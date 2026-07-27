from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from datetime import date
from decimal import Decimal

from candidates.models import Candidate, Application, CandidateStatus
from jobs.models import Job
from common.utils_csv import generate_csv_response, parse_csv_from_request, get_choice
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
    GET /api/v1/candidates/export/?status=screening&job_id=uuid
    Download role-scoped candidates (incl. talent pool) as CSV.
    All authenticated roles allowed (recruiters see assigned-jobs' candidates + pool).
    Uses same Q-filter pattern as CandidateViewSet.get_queryset().
    Optional filters (?status=, ?job_id=) apply to applications (excludes pure pool).
    Logs the export count. See docs/candidates.md for full RBAC/CSV contract.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = Candidate.objects.filter(
            is_deleted=False, 
            organization=user.organization
        ).prefetch_related('applications__job')

        if user.role == UserRole.ADMIN:
            pass  # sees all org candidates + pool
        elif user.role == UserRole.MANAGER:
            qs = qs.filter(
                Q(applications__job__created_by=user) | Q(applications__isnull=True)
            ).distinct()
        elif user.role == UserRole.RECRUITER:
            qs = qs.filter(
                Q(applications__job__assigned_recruiters=user) | Q(applications__isnull=True)
            ).distinct()
        # Note: Matches CandidateViewSet.get_queryset() exactly for RBAC

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
                c.current_ctc, c.expected_ctc, c.notice_period,
                status, share_date, feedback,
                job_title,
            ])

        log_action(user, 'exported', 'Candidate', None, f"Exported {len(rows)} candidates (incl. pool)")
        return generate_csv_response('candidates_export.csv', CANDIDATE_EXPORT_HEADERS, rows)


class CandidateImportView(APIView):
    """
    POST /api/v1/candidates/import/
    Upload CSV or Excel (.xlsx, .xls) for bulk create of candidates (pool or job-linked).
    All authenticated roles allowed (recruiters can import to pool or jobs they are assigned to via M2M check).
    Required: candidate_name, email, contact (validated by parser against normalized headers).
    job_title optional (iexact); creates Application with first_stage from Job.DEFAULT_STAGES equiv + status.
    Uses safe_float (coerced to Decimal for model), get_choice for status, dedup by (email+org), row-indexed errors (start=2).
    Response: 201 full or 207 partial. Logs summary with counts. Recruiter job guard retained.
    See docs/candidates.md for full contract (incl. normalized headers, _get_choice notes).
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
                        dob=row.get('dob') or None,
                        doc=row.get('doc') or None,
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
                    status_val = get_choice(
                        row.get('status'),
                        CandidateStatus.choices,
                        CandidateStatus.SCREENING.value
                    )
                    Application.objects.create(
                        candidate=candidate,
                        job=job,
                        current_stage=first_stage,
                        status=status_val,
                        feedback=row.get('feedback', ''),
                        share_date=row.get('share_date') or date.today(),
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
