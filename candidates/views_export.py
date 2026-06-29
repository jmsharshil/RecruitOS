from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from candidates.models import Candidate, CandidateStatus
from jobs.models import Job
from common.utils_csv import generate_csv_response, parse_csv_from_request
from common.permissions import IsAdminOrManager
from audit.utils import log_action

CANDIDATE_EXPORT_HEADERS = [
    'candidate_name', 'profile_name', 'current_company', 'current_profile',
    'experience', 'current_location', 'preferred_location',
    'education', 'college', 'contact', 'email',
    'current_ctc', 'expected_ctc', 'notice_period',
    'status', 'share_date', 'feedback', 'job_title',
]

CANDIDATE_IMPORT_REQUIRED = [
    'candidate_name', 'email', 'contact', 'job_title',
]


class CandidateExportView(APIView):
    """
    GET /api/v1/candidates/export/
    Download all visible candidates as a CSV file.
    Optional query params: ?status=screening&job_id=<uuid>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.models import UserRole

        qs = Candidate.objects.filter(is_deleted=False, organization=request.user.organization).select_related('job', 'current_stage')

        user = request.user
        if user.role == UserRole.MANAGER:
            qs = qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            qs = qs.filter(job__assigned_recruiters=user)

        # Optional filters
        status_filter = request.query_params.get('status')
        job_id = request.query_params.get('job_id')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if job_id:
            qs = qs.filter(job__id=job_id)

        rows = []
        for c in qs:
            rows.append([
                c.candidate_name, c.profile_name, c.current_company, c.current_profile,
                c.experience, c.current_location, c.preferred_location,
                c.education, c.college, c.contact, c.email,
                c.current_ctc, c.expected_ctc, c.notice_period,
                c.status, c.share_date, c.feedback,
                c.job.title if c.job else '',
            ])

        log_action(request.user, 'exported', 'Candidate', None, f"Exported {len(rows)} candidates")
        return generate_csv_response('candidates_export.csv', CANDIDATE_EXPORT_HEADERS, rows)


class CandidateImportView(APIView):
    """
    POST /api/v1/candidates/import/
    Upload a CSV to bulk-create candidates.
    The CSV must have at minimum: candidate_name, email, contact, job_title
    """
    permission_classes = [IsAdminOrManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=CANDIDATE_IMPORT_REQUIRED)
        if error:
            return Response({"error": error}, status=400)

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(rows, start=2):  # row 1 = header
            job_title = row.get('job_title', '').strip()
            job = Job.objects.filter(title__iexact=job_title, organization=request.user.organization).first()
            if not job:
                errors.append({"row": i, "error": f"Job '{job_title}' not found."})
                skipped += 1
                continue

            # Skip duplicates by email + job
            if Candidate.objects.filter(email=row.get('email', '').strip(), job=job).exists():
                errors.append({"row": i, "error": f"Candidate with email '{row.get('email')}' already exists for this job."})
                skipped += 1
                continue

            try:
                Candidate.objects.create(
                    job=job,
                    candidate_name=row.get('candidate_name', '').strip(),
                    profile_name=row.get('profile_name', row.get('candidate_name', '')).strip(),
                    current_company=row.get('current_company', '').strip(),
                    current_profile=row.get('current_profile', '').strip(),
                    experience=row.get('experience', '').strip(),
                    current_location=row.get('current_location', '').strip(),
                    preferred_location=row.get('preferred_location', '').strip(),
                    education=row.get('education', '').strip(),
                    college=row.get('college', '').strip(),
                    contact=row.get('contact', '').strip(),
                    email=row.get('email', '').strip(),
                    current_ctc=row.get('current_ctc') or 0,
                    expected_ctc=row.get('expected_ctc') or 0,
                    notice_period=row.get('notice_period', '').strip(),
                    feedback=row.get('feedback', '').strip(),
                    status=row.get('status', CandidateStatus.SCREENING),
                    created_by=request.user,
                    organization=request.user.organization,
                )
                created += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
                skipped += 1

        log_action(request.user, 'imported', 'Candidate', None, f"Imported {created} candidates from CSV")
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
