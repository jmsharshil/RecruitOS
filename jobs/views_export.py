from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from decimal import Decimal
from django.db import transaction
from accounts.models import UserRole

from jobs.models import Job, Stage, JobStatus, HiringFor, Priority, JobTypes, JobModes, DEFAULT_STAGES
from clients.models import Client
from common.utils_csv import generate_csv_response, parse_csv_from_request
from common.permissions import IsAdminOrManager
from audit.utils import log_action

JOB_EXPORT_HEADERS = [
    'title', 'min_experience', 'max_experience', 'location', 'openings', 'priority',
    'job_type', 'job_mode', 'hiring_for', 'client_name', 'status', 'skills',
    'education', 'budget', 'description',
]

JOB_IMPORT_REQUIRED = [
    'title', 'min_experience', 'max_experience', 'location',
]


class JobExportView(APIView):
    """
    GET /api/v1/jobs/export/?status=open
    Download role-scoped jobs as CSV (ADMIN= all org jobs; MANAGER=created_by=self).
    Uses IsAdminOrManager (blocks recruiters). Matches CandidateExportView QS + UserRole.
    Supports optional ?status= filter. Logs export action. See docs/jobs.md.
    """
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        qs = Job.objects.select_related('client').filter(
            is_deleted=False, organization=request.user.organization
        )
        user = request.user
        if user.role == UserRole.MANAGER:
            qs = qs.filter(created_by=user)
        # ADMIN sees all org jobs; RECRUITER blocked by IsAdminOrManager
        # Note: Matches FDD RBAC; aligned with CandidateExportView QS pattern

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        rows = []
        for j in qs:
            rows.append([
                j.title, j.min_experience, j.max_experience, j.location, j.openings, j.priority,
                j.job_type, j.job_mode, j.hiring_for,
                j.client.company_name if j.client else '',
                j.status,
                ', '.join(j.skills) if isinstance(j.skills, list) else (j.skills or ''),
                j.education, float(j.budget or 0), j.description or '',
            ])

        log_action(request.user, 'exported', 'Job', None, f"Exported {len(rows)} jobs")
        return generate_csv_response('jobs_export.csv', JOB_EXPORT_HEADERS, rows)


class JobImportView(APIView):
    """
    POST /api/v1/jobs/import/
    Upload CSV to bulk-create jobs (Admin/Manager only). Supports partial success (207).
    Required columns: title, min_experience, max_experience, location.
    Optional: client_name (iexact lookup with warning), skills (comma sep), status/priority/job_type/job_mode/hiring_for (with fallback to defaults),
    budget (Decimal), education, description, openings.
    Dedup by title (org-scoped). Auto-creates DEFAULT_STAGES. Row errors 1-based (start=2).
    See docs/jobs.md for full contract.
    """
    permission_classes = [IsAdminOrManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=JOB_IMPORT_REQUIRED)
        if error:
            raise ValidationError({"error": error})

        created, skipped, errors = 0, 0, []

        # Helper for safe choice lookup (case-insensitive on value or label)
        def _get_choice(val, choices, default):
            if not val:
                return default
            v = str(val).strip().lower()
            for c_val, c_disp in choices:
                if v in (c_val.lower(), str(c_disp).lower()):
                    return c_val
            return default

        for i, row in enumerate(rows, start=2):  # row 1 = header
            title = row.get('title', '').strip()
            if not title:
                errors.append({"row": i, "error": "Missing required title"})
                skipped += 1
                continue

            # Dedup check (org + title) - improves on model implicit uniqueness
            if Job.objects.filter(
                title__iexact=title,
                organization=request.user.organization,
                is_deleted=False
            ).exists():
                errors.append({"row": i, "error": f"Job with title '{title}' already exists."})
                skipped += 1
                continue

            client_name = row.get('client_name', '').strip()
            client = None
            if client_name:
                client = Client.objects.filter(
                    company_name__iexact=client_name,
                    is_deleted=False,
                    organization=request.user.organization
                ).first()
                if not client:
                    errors.append({"row": i, "error": f"Client '{client_name}' not found. Job will be created without a client."})

            skills_raw = row.get('skills', '')
            skills = [s.strip() for s in skills_raw.split(',') if s.strip()] if skills_raw else []

            try:
                min_exp = int(row.get('min_experience', 0) or 0)
                max_exp = int(row.get('max_experience', 0) or 0)
                openings = int(row.get('openings', 1) or 1)
                # Use Decimal for budget (model field)
                budget_raw = row.get('budget', '0')
                try:
                    budget = Decimal(str(budget_raw).replace(',', ''))
                except:
                    budget = Decimal('0')

                status = _get_choice(row.get('status'), JobStatus.choices, JobStatus.OPEN.value)
                priority = _get_choice(row.get('priority'), Priority.choices, Priority.MEDIUM.value)
                job_type = _get_choice(row.get('job_type'), JobTypes.choices, JobTypes.PERMANENT.value)
                job_mode = _get_choice(row.get('job_mode'), JobModes.choices, JobModes.OFFICE.value)
                hiring_for = _get_choice(row.get('hiring_for'), HiringFor.choices, HiringFor.SELF.value)

                education = row.get('education', '').strip()
                description = row.get('description', '').strip() or 'Imported via CSV'

                with transaction.atomic():
                    job = Job.objects.create(
                        title=title,
                        min_experience=min_exp,
                        max_experience=max_exp,
                        location=row.get('location', '').strip(),
                        openings=openings,
                        priority=priority,
                        job_type=job_type,
                        job_mode=job_mode,
                        hiring_for=hiring_for,
                        client=client,
                        status=status,
                        skills=skills,
                        education=education,
                        budget=budget,
                        description=description,
                        created_by=request.user,
                        organization=request.user.organization,
                    )

                    # Auto-create default stages (matches JobViewSet.perform_create)
                    for stage_data in DEFAULT_STAGES:
                        Stage.objects.create(
                            job=job,
                            created_by=request.user,
                            organization=job.organization,
                            **stage_data
                        )
                created += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
                skipped += 1

        log_action(
            request.user, 'imported', 'Job', None,
            f"Imported {created} jobs from CSV (skipped: {skipped})"
        )
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
