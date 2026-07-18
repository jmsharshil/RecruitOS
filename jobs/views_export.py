from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

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
    GET /api/v1/jobs/export/
    Download visible jobs (role-scoped) as CSV. Supports ?status=open filter.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.models import UserRole

        qs = Job.objects.select_related('client').filter(
            is_deleted=False, organization=request.user.organization
        )
        user = request.user
        if user.role == UserRole.MANAGER:
            qs = qs.filter(created_by=user)
        elif user.role == UserRole.RECRUITER:
            qs = qs.filter(assigned_recruiters=user)

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
    Upload CSV to bulk-create jobs (Admin/Manager only).
    See docs/jobs.md for column details and optional fields.
    """
    permission_classes = [IsAdminOrManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=JOB_IMPORT_REQUIRED)
        if error:
            return Response({"error": error}, status=400)

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(rows, start=2):
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
                budget = float(row.get('budget', 0) or 0)

                status_val = row.get('status', '').strip().lower()
                status = status_val if status_val in [c[0] for c in JobStatus.choices] else JobStatus.OPEN.value

                hiring_for_val = row.get('hiring_for', '').strip().lower()
                hiring_for = hiring_for_val if hiring_for_val in [c[0] for c in HiringFor.choices] else HiringFor.SELF.value

                priority_val = row.get('priority', '').strip().lower()
                priority = priority_val if priority_val in [c[0] for c in Priority.choices] else Priority.MEDIUM.value

                job_type_val = row.get('job_type', '').strip().lower()
                job_type = job_type_val if job_type_val in [c[0] for c in JobTypes.choices] else JobTypes.PERMANENT.value

                job_mode_val = row.get('job_mode', '').strip().lower()
                job_mode = job_mode_val if job_mode_val in [c[0] for c in JobModes.choices] else JobModes.OFFICE.value

                education = row.get('education', '').strip()
                description = row.get('description', '').strip()

                job = Job.objects.create(
                    title=row.get('title', '').strip(),
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

                # Auto-create default stages (same as JobViewSet.perform_create)
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

        log_action(request.user, 'imported', 'Job', None, f"Imported {created} jobs from CSV")
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
