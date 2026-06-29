from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from clients.models import Client, ClientStatus
from common.utils_csv import generate_csv_response, parse_csv_from_request
from common.permissions import IsAdmin
from audit.utils import log_action

CLIENT_EXPORT_HEADERS = [
    'client_id', 'company_name', 'client_name', 'email', 'contact',
    'industry', 'city', 'state', 'country', 'status',
    'website', 'gst_number', 'agreement_date', 'payment_period_days',
    'replacement_period_days',
]

CLIENT_IMPORT_REQUIRED = [
    'company_name', 'client_name', 'email', 'contact', 'industry',
]


class ClientExportView(APIView):
    """
    GET /api/v1/clients/export/
    Download all clients as a CSV file.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Client.objects.filter(is_deleted=False, organization=request.user.organization)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        rows = []
        for c in qs:
            rows.append([
                c.client_id, c.company_name, c.client_name, c.email, c.contact,
                c.industry, c.city, c.state, c.country, c.status,
                c.website, c.gst_number, c.agreement_date, c.payment_period_days,
                c.replacement_period_days,
            ])

        log_action(request.user, 'exported', 'Client', None, f"Exported {len(rows)} clients")
        return generate_csv_response('clients_export.csv', CLIENT_EXPORT_HEADERS, rows)


class ClientImportView(APIView):
    """
    POST /api/v1/clients/import/
    Upload a CSV to bulk-create clients (Admin only).
    Required columns: company_name, client_name, email, contact, industry
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=CLIENT_IMPORT_REQUIRED)
        if error:
            return Response({"error": error}, status=400)

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(rows, start=2):
            email = row.get('email', '').strip()
            if Client.objects.filter(email=email, is_deleted=False, organization=request.user.organization).exists():
                errors.append({"row": i, "error": f"Client with email '{email}' already exists."})
                skipped += 1
                continue

            try:
                Client.objects.create(
                    company_name=row.get('company_name', '').strip(),
                    client_name=row.get('client_name', '').strip(),
                    email=email,
                    contact=row.get('contact', '').strip(),
                    industry=row.get('industry', '').strip(),
                    city=row.get('city', '').strip(),
                    state=row.get('state', '').strip(),
                    country=row.get('country', '').strip(),
                    website=row.get('website', '').strip(),
                    gst_number=row.get('gst_number', '').strip(),
                    status=row.get('status', ClientStatus.ACTIVE),
                    payment_period_days=row.get('payment_period_days') or None,
                    replacement_period_days=row.get('replacement_period_days') or None,
                    created_by=request.user,
                    organization=request.user.organization,
                )
                created += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
                skipped += 1

        log_action(request.user, 'imported', 'Client', None, f"Imported {created} clients from CSV")
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
