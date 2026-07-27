from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from datetime import date
from decimal import Decimal

from candidates.models import Candidate, Application, CandidateStatus
from jobs.models import Job, Stage, DEFAULT_STAGES
from common.utils_csv import generate_csv_response, parse_csv_from_request, get_choice
from common.serializers import DateParserField
from audit.utils import log_action
from candidates.utils import safe_float
from accounts.models import UserRole

CANDIDATE_EXPORT_HEADERS = [
    'candidate_name', 'profile_name', 'current_company', 'current_profile',
    'experience', 'current_location', 'preferred_location',
    'education', 'college', 'contact', 'email', 'dob', 'doc',
    'current_ctc', 'expected_ctc', 'notice_period',
    'status', 'share_date', 'feedback', 'job_title',
]

CANDIDATE_IMPORT_REQUIRED = [
    'candidate_name', 'email', 'contact',
]


class CandidateExportView(APIView):
    """
    GET /api/v1/candidates/export/?status=screening&job_id=uuid&template=1
    Download role-scoped candidates (incl. talent pool) as CSV. All authenticated roles allowed
    (recruiters see full org pool per CandidateViewSet.get_queryset()). Uses exact same
    role logic as CandidateViewSet. Optional filters (?status=, ?job_id=) apply to applications
    (excludes pure pool if filtered). Supports ?template=1. Logs action. See docs/candidates.md.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Supports ?template=1 (sample row, no DB hit), ?format=xlsx, ?status=, ?job_id=.
        Uses exact same Q-filter/RBAC as CandidateViewSet.get_queryset() for pool+assigned.
        Filters on status/job_id exclude pure pool candidates. Updated filename per format."""
        is_template = request.query_params.get('template') in ('1', 'true', 'yes')
        export_format = request.query_params.get('format', 'csv').lower()
        if export_format not in ('csv', 'xlsx'):
            export_format = 'csv'

        if is_template:
            # Sample data for template - can be used for pool (job_title empty) or with job_title for application linking
            rows = [[
                'Rahul Sharma', 'Software Engineer', 'Tech Solutions Ltd', 'Senior Backend Dev',
                '6 years', 'Bangalore', 'Bangalore, Remote',
                'B.Tech in Computer Science', 'IIT Bombay', '+919876543210', 'rahul.sharma@email.com',
                '1995-05-15', '2024-01-10', 1200000, 1800000, '30 days',
                'SCREENING', '2024-01-10', 'Strong Python/Django background', 'Senior Python Developer'
            ]]
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'candidates_import_template.{ext}'
            log_msg = "Downloaded candidate import template"
        else:
            user = request.user
            qs = Candidate.objects.filter(
                is_deleted=False, 
                organization=user.organization
            ).prefetch_related('applications__job')

            if user.role == UserRole.ADMIN:
                pass  # full org
            elif user.role == UserRole.MANAGER:
                qs = qs.filter(
                    Q(applications__job__created_by=user) | Q(applications__isnull=True)
                ).distinct()
            elif user.role == UserRole.RECRUITER:
                # Recruiters see full org talent pool + candidates from their assigned jobs
                # (consistent with updated CandidateViewSet.get_queryset())
                qs = qs.filter(
                    Q(applications__isnull=True) |
                    Q(applications__job__assigned_recruiters=user)
                ).distinct()
            # Note: Exactly matches CandidateViewSet.get_queryset() RBAC for pool + assigned jobs

            # Optional filters (these will exclude pool candidates)
            status_filter = request.query_params.get('status')
            job_id = request.query_params.get('job_id')
            if status_filter:
                qs = qs.filter(
                    applications__status=status_filter,
                    applications__is_deleted=False
                )
            if job_id:
                qs = qs.filter(applications__job_id=job_id)

            rows = []
            for c in qs:
                # Use cached prefetched applications, ignore soft-deleted (pool candidates have none)
                apps = [a for a in c.applications.all() if not getattr(a, 'is_deleted', False)]
                app = apps[0] if apps else None
                status = getattr(app, 'status', 'POOL')
                share_date = getattr(app, 'share_date', '')
                feedback = getattr(app, 'feedback', '')
                job_title = getattr(app, 'job', None).title if app and getattr(app, 'job', None) else 'Talent Pool'

                rows.append([
                    c.candidate_name, c.profile_name, c.current_company, c.current_profile,
                    c.experience, c.current_location, c.preferred_location or '',
                    c.education, c.college or '', c.contact, c.email,
                    c.dob, c.doc,
                    float(c.current_ctc or 0), float(c.expected_ctc or 0), c.notice_period,
                    status, share_date, feedback,
                    job_title,
                ])
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'candidates_export.{ext}'
            log_msg = f"Exported {len(rows)} candidates (incl. pool)"

        log_action(request.user, 'exported', 'Candidate', None, log_msg)
        return generate_csv_response(filename, CANDIDATE_EXPORT_HEADERS, rows, export_format=export_format)


class CandidateImportView(APIView):
    """
    POST /api/v1/candidates/import/
    Upload CSV or Excel (.xlsx/.xls) for bulk create of candidates (pool or job-linked).
    All authenticated roles allowed (recruiters can import to pool or jobs they are assigned to via M2M).
    Required: candidate_name, email, contact (parser validates normalized headers).
    job_title optional (iexact lookup); creates Application linked to first_stage + status (get_choice).
    Uses DateParserField for dob/doc/share_date (flexible formats), safe_float->Decimal for CTCs,
    dedup by (email+org), recruiter RBAC guard. Transaction per record. Row errors indexed from 2.
    Response: 201 full success or 207 partial with errors list. Logs summary. See docs/candidates.md.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        headers, rows, error = parse_csv_from_request(request, required_fields=CANDIDATE_IMPORT_REQUIRED)
        if error:
            raise ValidationError({"error": error})

        created_candidates = 0
        created_applications = 0
        skipped = 0
        errors = []
        date_parser = DateParserField()

        for i, row in enumerate(rows, start=2):  # row 1 = header; works for Excel too
            name = row.get('candidate_name', '').strip()
            email = row.get('email', '').strip().lower()
            contact = row.get('contact', '').strip()
            if not all([name, email, contact]):
                errors.append({"row": i, "error": "Missing candidate_name, email or contact"})
                skipped += 1
                continue

            job_title = row.get('job_title', '').strip()
            job = None
            if job_title:
                job = Job.objects.filter(
                    title__iexact=job_title,
                    organization=user.organization,
                    is_deleted=False
                ).first()
                if not job:
                    errors.append({"row": i, "error": f"Job '{job_title}' not found."})
                    skipped += 1
                    continue
                # RBAC: Recruiters can only link to jobs they are assigned to
                if user.role == UserRole.RECRUITER and not job.assigned_recruiters.filter(id=user.id).exists():
                    errors.append({"row": i, "error": f"Recruiter not assigned to job '{job_title}'. Access denied."})
                    skipped += 1
                    continue

            # Get or create candidate (pool-friendly, dedup by email+org)
            candidate = Candidate.objects.filter(
                email=email,
                organization=user.organization,
                is_deleted=False
            ).first()
            if not candidate:
                try:
                    # Flexible date parsing for dob/doc
                    dob = None
                    dob_raw = row.get('dob')
                    if dob_raw and str(dob_raw).strip() not in ('', 'None', 'null'):
                        try:
                            dob = date_parser.to_internal_value(str(dob_raw).strip())
                        except Exception:
                            dob = None

                    doc = None
                    doc_raw = row.get('doc')
                    if doc_raw and str(doc_raw).strip() not in ('', 'None', 'null'):
                        try:
                            doc = date_parser.to_internal_value(str(doc_raw).strip())
                        except Exception:
                            doc = None

                    with transaction.atomic():
                        candidate = Candidate.objects.create(
                            candidate_name=name,
                            profile_name=row.get('profile_name', name).strip(),
                            current_profile=row.get('current_profile', 'Not provided'),
                            current_company=row.get('current_company', 'Not provided'),
                            experience=row.get('experience', '0 years'),
                            current_location=row.get('current_location', 'Not specified'),
                            preferred_location=row.get('preferred_location', ''),
                            education=row.get('education', ''),
                            college=row.get('college', ''),
                            contact=contact,
                            email=email,
                            dob=dob,
                            doc=doc,
                            current_ctc=Decimal(safe_float(row.get('current_ctc')) or 0),
                            expected_ctc=Decimal(safe_float(row.get('expected_ctc')) or 0),
                            notice_period=row.get('notice_period', 'Not specified'),
                            reason_for_change=row.get('reason_for_change', 'Imported via file'),
                            resume_file_name=row.get('resume_file_name', ''),
                            uploaded_by=user,
                            organization=user.organization,
                        )
                    created_candidates += 1
                except Exception as e:
                    errors.append({"row": i, "error": f"Create candidate failed: {str(e)}"})
                    skipped += 1
                    continue
            else:
                # Optionally update existing; for now skip to avoid partial updates
                pass

            if job:
                # Create application if not exists (unique per candidate-job via Meta)
                if Application.objects.filter(
                    candidate=candidate,
                    job=job,
                    organization=user.organization,
                    is_deleted=False
                ).exists():
                    errors.append({"row": i, "error": f"Application already exists for {email} on job '{job_title}'."})
                    skipped += 1
                    continue

                try:
                    first_stage = job.stages.filter(is_deleted=False).order_by('order').first()
                    if not first_stage:
                        # Fallback: create default stages if missing (consistent with JobImportView)
                        for stage_data in DEFAULT_STAGES:
                            Stage.objects.create(
                                job=job,
                                created_by=user,
                                organization=user.organization,
                                **stage_data
                            )
                        first_stage = job.stages.filter(is_deleted=False).order_by('order').first()

                    status_val = get_choice(
                        row.get('status'),
                        CandidateStatus.choices,
                        CandidateStatus.SCREENING.value
                    )

                    # Flexible parsing for share_date
                    share_date = date.today()
                    share_raw = row.get('share_date')
                    if share_raw and str(share_raw).strip() not in ('', 'None', 'null'):
                        try:
                            parsed = date_parser.to_internal_value(str(share_raw).strip())
                            if parsed:
                                share_date = parsed
                        except Exception:
                            pass  # fallback to today

                    with transaction.atomic():
                        Application.objects.create(
                            candidate=candidate,
                            job=job,
                            current_stage=first_stage,
                            status=status_val,
                            feedback=row.get('feedback', ''),
                            share_date=share_date,
                            organization=user.organization,
                        )
                    created_applications += 1
                except Exception as e:
                    errors.append({"row": i, "error": f"Create application failed: {str(e)}"})
                    skipped += 1
                    continue

        log_action(
            user,
            'imported',
            'Candidate/Application',
            None,
            f"Imported {created_candidates} candidates and {created_applications} applications from file (skipped: {skipped})"
        )
        status_code = 207 if errors else 201
        return Response({
            "created_candidates": created_candidates,
            "created_applications": created_applications,
            "skipped": skipped,
            "errors": errors,
        }, status=status_code)
