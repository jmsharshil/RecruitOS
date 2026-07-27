from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from clients.models import Client, ClientStatus
from common.utils_csv import generate_csv_response, parse_csv_from_request
from common.permissions import IsAdmin
from audit.utils import log_action

CLIENT_EXPORT_HEADERS = [
    'client_id', 'company_name', 'client_name', 'email', 'alternative_email',
    'contact', 'alternative_contact', 'website', 'linkedin', 'street',
    'city', 'state', 'country', 'postal_code', 'client_location',
    'industry', 'gst_number', 'status', 'agreement_date', 'payment_period_days',
    'replacement_period_days', 'commercial_decided', 'agreement_document_name',
    'notes',
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
                c.client_id, c.company_name, c.client_name, c.email, c.alternative_email or '',
                c.contact, c.alternative_contact or '', c.website or '', c.linkedin or '', c.street or '',
                c.city, c.state, c.country, c.postal_code or '', c.client_location or '',
                c.industry, c.gst_number or '', c.status, c.agreement_date, c.payment_period_days,
                c.replacement_period_days, c.commercial_decided, c.agreement_document_name or '',
                c.notes or '',
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
            email = row.get('email', '').strip().lower()
            if Client.objects.filter(email__iexact=email, is_deleted=False, organization=request.user.organization).exists():
                errors.append({"row": i, "error": f"Client with email '{email}' already exists (org-scoped)."})
                skipped += 1
                continue

            try:
                status_val = row.get('status', 'active').lower().strip()
                if status_val not in dict(ClientStatus.choices):
                    status_val = ClientStatus.ACTIVE

                Client.objects.create(
                    company_name=row.get('company_name', '').strip(),
                    client_name=row.get('client_name', '').strip(),
                    email=email,
                    alternative_email=row.get('alternative_email', '').strip() or None,
                    contact=row.get('contact', '').strip(),
                    alternative_contact=row.get('alternative_contact', '').strip() or None,
                    website=row.get('website', '').strip() or None,
                    linkedin=row.get('linkedin', '').strip() or None,
                    street=row.get('street', '').strip(),
                    city=row.get('city', '').strip(),
                    state=row.get('state', '').strip(),
                    country=row.get('country', '').strip(),
                    postal_code=row.get('postal_code', '').strip() or None,
                    client_location=row.get('client_location', '').strip() or None,
                    industry=row.get('industry', '').strip(),
                    gst_number=row.get('gst_number', '').strip() or None,
                    status=status_val,
                    agreement_date=row.get('agreement_date') or None,  # parsed by model or add DateParser if needed
                    payment_period_days=row.get('payment_period_days') or None,
                    replacement_period_days=row.get('replacement_period_days') or None,
                    commercial_decided=row.get('commercial_decided', 'false').lower() in ('true', '1', 'yes'),
                    agreement_document_name=row.get('agreement_document_name', '').strip() or None,
                    notes=row.get('notes', '').strip(),
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
