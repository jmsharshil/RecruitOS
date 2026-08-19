from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from decimal import Decimal
from django.db import transaction
from accounts.models import UserRole

from jobs.models import Job, Stage, JobStatus, HiringFor, Priority, JobTypes, JobModes, DEFAULT_STAGES
from clients.models import Client
from common.utils_csv import generate_csv_response, parse_csv_from_request, get_choice
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
        """Supports ?template=1 (sample row, no DB hit) and ?format=xlsx (or csv).
        Uses same RBAC QS as JobViewSet. Logs action (separate msg for template)."""
        is_template = request.query_params.get('template') in ('1', 'true', 'yes')
        export_format = request.query_params.get('format', 'csv').lower()
        if export_format not in ('csv', 'xlsx'):
            export_format = 'csv'

        if is_template:
            # Sample data for template - note skills as comma string (parser will split)
            rows = [[
                'Senior Python Developer', 3, 7, 'Bangalore', 2, 'HIGH',
                'PERMANENT', 'HYBRID', 'SELF', 'Acme Corp', 'OPEN',
                'Python, Django, REST API, PostgreSQL, AWS', 'B.Tech Computer Science',
                1500000, 'Looking for experienced backend engineer with strong Python skills.'
            ]]
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'jobs_import_template.{ext}'
            log_msg = "Downloaded job import template"
        else:
            qs = Job.objects.select_related('client').filter(
                is_deleted=False, organization=request.user.organization
            )
            # ADMIN and MANAGER see all org jobs; RECRUITER blocked by IsAdminOrManager
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
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'jobs_export.{ext}'
            log_msg = f"Exported {len(rows)} jobs"

        log_action(request.user, 'exported', 'Job', None, log_msg)
        return generate_csv_response(filename, JOB_EXPORT_HEADERS, rows, export_format=export_format)


class JobImportView(APIView):
    """
    POST /api/v1/jobs/import/
    Upload CSV or Excel (.xlsx, .xls) for bulk create of jobs (Admin/Manager only; recruiters blocked).
    Required: title, min_experience, max_experience, location (validated by parser on normalized headers).
    Optional: client_name (lookup or warning), skills (comma-split), status/priority/etc via get_choice (defaults provided),
    budget as Decimal, etc. Dedup by title__iexact+org. Auto-creates stages from DEFAULT_STAGES. Row errors start at 2.
    Response: 201 or 207 partial with errors list. Uses transaction per job. See docs/jobs.md.
    """
    permission_classes = [IsAdminOrManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=JOB_IMPORT_REQUIRED)
        if error:
            raise ValidationError({"error": error})

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(rows, start=2):  # row 1 = header; works for Excel too
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

                status = get_choice(row.get('status'), JobStatus.choices, JobStatus.OPEN.value)
                priority = get_choice(row.get('priority'), Priority.choices, Priority.MEDIUM.value)
                job_type = get_choice(row.get('job_type'), JobTypes.choices, JobTypes.PERMANENT.value)
                job_mode = get_choice(row.get('job_mode'), JobModes.choices, JobModes.OFFICE.value)
                hiring_for = get_choice(row.get('hiring_for'), HiringFor.choices, HiringFor.SELF.value)

                education = row.get('education', '').strip()
                description = row.get('description', '').strip() or 'Imported via file'

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
            f"Imported {created} jobs from file (skipped: {skipped})"
        )
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
