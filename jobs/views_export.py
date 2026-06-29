from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from jobs.models import Job, JobStatus, HiringFor
from clients.models import Client
from common.utils_csv import generate_csv_response, parse_csv_from_request
from common.permissions import IsAdminOrManager
from audit.utils import log_action

JOB_EXPORT_HEADERS = [
    'title', 'experience', 'location', 'hiring_for',
    'client_name', 'status', 'skills', 'description',
]

JOB_IMPORT_REQUIRED = [
    'title', 'experience', 'location',
]


class JobExportView(APIView):
    """
    GET /api/v1/jobs/export/
    Download all visible jobs as a CSV file.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.models import UserRole

        qs = Job.objects.select_related('client').filter(organization=request.user.organization)
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
                j.title, j.experience, j.location, j.hiring_for,
                j.client.company_name if j.client else '',
                j.status,
                ', '.join(j.skills) if isinstance(j.skills, list) else j.skills,
                j.description,
            ])

        log_action(request.user, 'exported', 'Job', None, f"Exported {len(rows)} jobs")
        return generate_csv_response('jobs_export.csv', JOB_EXPORT_HEADERS, rows)


class JobImportView(APIView):
    """
    POST /api/v1/jobs/import/
    Upload a CSV to bulk-create jobs (Admin/Manager only).
    Required columns: title, experience, location
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
                client = Client.objects.filter(company_name__iexact=client_name, is_deleted=False, organization=request.user.organization).first()
                if not client:
                    errors.append({"row": i, "error": f"Client '{client_name}' not found. Job will be created without a client."})

            skills_raw = row.get('skills', '')
            skills = [s.strip() for s in skills_raw.split(',') if s.strip()] if skills_raw else []

            try:
                Job.objects.create(
                    title=row.get('title', '').strip(),
                    experience=row.get('experience', '').strip(),
                    location=row.get('location', '').strip(),
                    hiring_for=row.get('hiring_for', HiringFor.SELF),
                    client=client,
                    status=row.get('status', JobStatus.OPEN),
                    skills=skills,
                    description=row.get('description', '').strip(),
                    created_by=request.user,
                    organization=request.user.organization,
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
