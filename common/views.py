from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from clients.views_export import CLIENT_EXPORT_HEADERS, CLIENT_IMPORT_REQUIRED
from jobs.views_export import JOB_EXPORT_HEADERS, JOB_IMPORT_REQUIRED
from candidates.views_export import CANDIDATE_EXPORT_HEADERS, CANDIDATE_IMPORT_REQUIRED


class ExportFormatsView(APIView):
    """
    GET /api/v1/export-formats/
    Returns available export formats, headers, required fields for import,
    and template/download URLs for Client, Job, and Candidate.
    Useful for frontend to dynamically show export options and download templates.
    Supports CSV and XLSX formats (XLSX via future extension of utils).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {
            "client": {
                "name": "Client",
                "formats": ["csv", "xlsx"],
                "export_headers": CLIENT_EXPORT_HEADERS,
                "import_required": CLIENT_IMPORT_REQUIRED,
                "export_url": "/api/v1/clients/export/",
                "import_url": "/api/v1/clients/import/",
                "template_url": "/api/v1/clients/export/?template=1",
                "description": "Export clients with full details. Template for bulk import."
            },
            "job": {
                "name": "Job",
                "formats": ["csv", "xlsx"],
                "export_headers": JOB_EXPORT_HEADERS,
                "import_required": JOB_IMPORT_REQUIRED,
                "export_url": "/api/v1/jobs/export/",
                "import_url": "/api/v1/jobs/import/",
                "template_url": "/api/v1/jobs/export/?template=1",
                "description": "Export jobs with skills, budget, client info. Admin/Manager only."
            },
            "candidate": {
                "name": "Candidate",
                "formats": ["csv", "xlsx"],
                "export_headers": CANDIDATE_EXPORT_HEADERS,
                "import_required": CANDIDATE_IMPORT_REQUIRED,
                "export_url": "/api/v1/candidates/export/",
                "import_url": "/api/v1/candidates/import/",
                "template_url": "/api/v1/candidates/export/?template=1",
                "description": "Export candidates (incl. talent pool). Supports job-specific filters."
            }
        }
        return Response(data)
