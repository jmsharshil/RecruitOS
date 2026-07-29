from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db import transaction
from accounts.models import UserRole

from clients.models import Client, ClientStatus
from common.utils_csv import generate_csv_response, parse_csv_from_request, get_choice
from common.serializers import DateParserField
from common.permissions import IsAdmin
from audit.utils import log_action

CLIENT_EXPORT_HEADERS = [
    'client_id', 'company_name', 'client_name', 'email',
    'contact', 'street',
    'city', 'state', 'country', 'postal_code',
    'industry', 'gst_number', 'status', 'agreement_date', 'payment_period_days',
    'replacement_period_days', 'commercial_decided', 'agreement_document_name',
    'notes',
]

CLIENT_IMPORT_REQUIRED = [
    'company_name', 'client_name', 'email', 'contact', 'industry',
]


class ClientExportView(APIView):
    """
    GET /api/v1/clients/export/?status=active&format=xlsx
    Download role-scoped clients as CSV/XLSX (ADMIN/MANAGER=full org; RECRUITER=clients linked to their jobs via reverse FK).
    Mirrors ClientViewSet.get_queryset() RBAC exactly. Supports ?template=1 (sample with text for commercial_decided), ?status= (case-insensitive via get_choice),
    ?format=xlsx (native types + buffer.seek(0)). commercial_decided changed to TextField.
    Includes all fields (agreement_document_name, commercial_decided etc). Logs action.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Supports ?template=1 (sample row, no DB hit) + ?format=xlsx + ?status=.
        Mirrors exact RBAC/QS from ClientViewSet.get_queryset() (ADMIN/MANAGER full, RECRUITER via jobs__assigned_recruiters).
        Status filter now uses get_choice for flexibility. Updated XLSX cleaning prevents corruption."""
        is_template = request.query_params.get('template') in ('1', 'true', 'yes')
        export_format = request.query_params.get('format', 'csv').lower()
        if export_format not in ('csv', 'xlsx'):
            export_format = 'csv'

        if is_template:
            # Sample data for template (commercial_decided now text, e.g. terms or "Yes")
            rows = [[
                'CLI-001', 'Acme Corp', 'John Doe', 'john@acmecorp.com', 'jane@acmecorp.com',
                '+1234567890', '+1987654321', 'https://acmecorp.com', 'https://linkedin.com/company/acme',
                '123 Business St', 'New York', 'NY', 'USA', '10001', 'New York Metro',
                'Technology', 'GSTIN123456789', 'ACTIVE', '2024-01-15', 30,
                45, 'Yes - 15% margin, net-30', 'agreement.pdf', 'Sample client notes for demo purposes.'
            ]]
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'clients_import_template.{ext}'
            log_msg = "Downloaded client import template"
        else:
            user = request.user
            qs = Client.objects.filter(
                is_deleted=False,
                organization=user.organization
            ).select_related('created_by')

            if user.role in (UserRole.ADMIN, UserRole.MANAGER):
                pass  # full org access
            elif user.role == UserRole.RECRUITER:
                qs = qs.filter(
                    jobs__is_deleted=False,
                    jobs__assigned_recruiters=user
                ).distinct()
            else:
                qs = qs.none()

            status_filter = request.query_params.get('status')
            if status_filter:
                # Use get_choice for case-insensitive match against choices (ACTIVE/active/on-hold)
                status_val = get_choice(status_filter, ClientStatus.choices, None)
                if status_val:
                    qs = qs.filter(status=status_val)

            rows = []
            for c in qs:
                # agreement_date remains date object (or None); util now handles natively for XLSX
                # commercial_decided is now TextField (string or empty)
                rows.append([
                    c.client_id, c.company_name, c.client_name, c.email, c.alternative_email or '',
                    c.contact, c.alternative_contact or '', c.website or '', c.linkedin or '', c.street or '',
                    c.city, c.state, c.country, c.postal_code or '', c.client_location or '',
                    c.industry, c.gst_number or '', c.status, c.agreement_date, c.payment_period_days,
                    c.replacement_period_days, c.commercial_decided or '', c.agreement_document_name or '',
                    c.notes or '',
                ])
            ext = 'xlsx' if export_format == 'xlsx' else 'csv'
            filename = f'clients_export.{ext}'
            log_msg = f"Exported {len(rows)} clients"

        log_action(request.user, 'exported', 'Client', None, log_msg)
        return generate_csv_response(filename, CLIENT_EXPORT_HEADERS, rows, export_format=export_format)


class ClientImportView(APIView):
    """
    POST /api/v1/clients/import/
    Upload a CSV/XLSX to bulk-create clients (Admin only).
    Required columns: company_name, client_name, email, contact, industry
    commercial_decided now accepts any text (terms decided); no longer bool-coerced.
    """
    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        headers, rows, error = parse_csv_from_request(request, required_fields=CLIENT_IMPORT_REQUIRED)
        if error:
            raise ValidationError({"error": error})

        created, skipped, errors = 0, 0, []

        date_parser = DateParserField()

        for i, row in enumerate(rows, start=2):  # row 1 = headers
            email = row.get('email', '').strip().lower()
            if not email:
                errors.append({"row": i, "error": "Missing required email"})
                skipped += 1
                continue

            if Client.objects.filter(
                email__iexact=email,
                is_deleted=False,
                organization=request.user.organization
            ).exists():
                errors.append({"row": i, "error": f"Client with email '{email}' already exists (org-scoped)."})
                skipped += 1
                continue

            try:
                # Flexible date parsing for agreement_date (supports multiple formats from CSV/Excel)
                agreement_date = None
                agr_raw = row.get('agreement_date')
                if agr_raw and str(agr_raw).strip() not in ('', 'None', 'null'):
                    try:
                        agreement_date = date_parser.to_internal_value(str(agr_raw).strip())
                    except Exception:
                        agreement_date = None  # fallback; could collect warning

                status_val = get_choice(
                    row.get('status'),
                    ClientStatus.choices,
                    ClientStatus.ACTIVE
                )

                payment_days = row.get('payment_period_days')
                replacement_days = row.get('replacement_period_days')
                try:
                    payment_period_days = int(payment_days) if payment_days and str(payment_days).strip() else None
                    replacement_period_days = int(replacement_days) if replacement_days and str(replacement_days).strip() else None
                except (ValueError, TypeError):
                    payment_period_days = replacement_period_days = None

                # commercial_decided now TextField (free text for terms decided, e.g. "15% margin")
                commercial_decided = str(row.get('commercial_decided', '')).strip()

                with transaction.atomic():  # atomic per client (consistent with JobImportView)
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
                        agreement_date=agreement_date,
                        payment_period_days=payment_period_days,
                        replacement_period_days=replacement_period_days,
                        commercial_decided=commercial_decided,
                        agreement_document_name=row.get('agreement_document_name', '').strip() or None,
                        notes=row.get('notes', '').strip(),
                        created_by=request.user,
                        organization=request.user.organization,
                    )
                created += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
                skipped += 1

        log_action(
            request.user, 'imported', 'Client', None,
            f"Imported {created} clients from file (skipped: {skipped})"
        )
        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }, status=207 if errors else 201)
