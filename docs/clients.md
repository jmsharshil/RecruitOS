# Clients Module Documentation

## Overview
Manages client companies that post job requirements. Linked to Jobs (FK), POCs (related_name='pocs'), Documents (related_name='documents'). All inherit `BaseModel` for org-scoping, soft-delete, audit timestamps. 

**Key Models**: `Client` (UUID PK, auto `client_id=CLI-XXXX` in `save()` with org-scoped `unique_together=('organization', 'client_id')`), `POC` (with `POCType`), `ClientDocument` (general FileField). Added `agreement_document` (FileField to 'client_agreements/') + `agreement_document_name` (CharField) via migrations 0002 and 0003. Like Candidate.resume, for easy upload of agreement during client **create** (multipart support via parser_classes on ViewSet + serializer auto-name from file).
- `clients/filters.py`: `ClientFilterSet` (status, industry/city/state/country icontains, date ranges, has_agreement, commercial_decided) registered on ViewSet.

**Choice Enums** (in models.py):
- `ClientStatus`: "active", "inactive", "on-hold" (default: "active")
- `POCType`: "hiring", "payment"

All fields support full body in create/update. `ClientDetailSerializer.to_internal_value` + `create` supports **nested** `pocs` (JSON) and `documents`; for files use multipart on create (for `agreement_document`) or dedicated `/documents/` action (now with MultiPartParser + auto `file_name`). Detail responses group POCs by type, include agreement doc, computed `stats`.

**Client Fields Reference** (all from `ClientDetailSerializer` + model; use this for API bodies):

| Field Name | Type | Required for Create? | Choices / Format | Default | Description / Notes |
|------------|------|-----------------------|------------------|---------|---------------------|
| `company_name` | string | **Yes** | - | - | Company legal name (unique-ish per org via business logic) |
| `client_name` | string | **Yes** | - | - | Primary contact name |
| `email` | email | **Yes** | valid email | - | Primary email (used for duplicate check in import) |
| `alternative_email` | email | No | - | "" | Secondary email |
| `contact` | string | **Yes** | phone-like | - | Primary phone |
| `alternative_contact` | string | No | - | "" | Secondary phone |
| `website` | url | No | valid URL | "" | Company website |
| `linkedin` | url | No | valid URL | "" | Company/profile LinkedIn |
| `street` | text | No | - | "" | Full street address |
| `city` | string | **Yes** (for most) | - | - | City |
| `state` | string | **Yes** | - | - | State/Province |
| `country` | string | **Yes** | - | - | Country |
| `postal_code` | string | No | - | "" | ZIP/Postal |
| `client_location` | string | No | - | "" | Specific office location |
| `industry` | string | **Yes** | - | - | e.g. "IT Services", "Finance" |
| `gst_number` | string | No | GST format | "" | Tax ID (India-specific) |
| `status` | string | No | `ClientStatus` choices | "active" | Use `/status/` action or PATCH |
| `agreement_date` | date | No | YYYY-MM-DD | null | Date of signed agreement |
| `payment_period_days` | integer | No | >0 | null | e.g. 30 (net terms) |
| `replacement_period_days` | integer | No | >0 | null | e.g. 90 (replacement guarantee) |
| `commercial_decided` | boolean | No | true/false | false | Flag for commercial terms finalized |
| `agreement_document` | file | No | multipart FileField | null | Main agreement/contract PDF; upload during create (multipart/form-data) or via PATCH; sets `agreement_document_name` automatically |
| `agreement_document_name` | string | No (auto) | - | "" | Auto-populated from uploaded filename (like Candidate.resume_file_name) |
| `notes` | text | No | - | "" | Internal notes (rich text possible) |
| `pocs` | array[object] | No (nested) | See POC table | [] | Nested array of POC objects (hiring + payment); auto-created on JSON create |
| `documents` | array[object] | No (nested) | See Document table | [] | Nested metadata/docs on create (limited for files); prefer `/documents/` action for general uploads |
| `client_id` | string | No (read-only) | CLI-0001 | auto | Auto-generated in `save()`; unique per org |
| `created_by` | UUID | No (read-only) | - | current user | Set in `perform_create` |
| `stats` | object | No (read-only) | - | computed | open_jobs, candidates_submitted, hired_count (in detail) |

**POC Fields** (used in nested or `/pocs/` actions; `POCSerializer = ModelSerializer(fields='__all__')` with read_only on internals):

| Field | Type | Required | Choices | Notes |
|-------|------|----------|---------|-------|
| `poc_type` | string | **Yes** | "hiring", "payment" | Groups in detail response |
| `name` | string | **Yes** | - | POC name |
| `email` | email | **Yes** | - | Used for `send_org_email(organization, to=poc.email, ...)` in tasks |
| `designation` | string | **Yes** | - | e.g. "Talent Acquisition Head" |
| `contact` | string | **Yes** | - | Phone |
| `linkedin` | url | No | - | Profile link |
| `description` | text | No | - | Notes on this POC |

**ClientDocument Fields**: `file` (FileField, multipart), `file_name` (auto or provided), read-only timestamps/id.

**Notes on Fields**:
- **Nested in Create Body**: `ClientDetailSerializer` supports `pocs: [{...}, {...}]` and `documents` in POST (validated, created atomically in `create()` override). Use dedicated actions for additional after create.
- Required for Import CSV: `company_name`, `client_name`, `email`, `contact`, `industry` (see `CLIENT_IMPORT_REQUIRED`).
- `client_id` generated like `CLI-0001`, `CLI-0002`... per org (last+1 logic in `save()`).
- All mutations log via `audit.log_action`. Soft-delete on destroy.
- Read-only fields (id, client_id, created_by, organization, is_deleted) ignored in writes.

**Error Handling (All Endpoints)**  
Normalized by `common.exceptions.custom_exception_handler` into:
```json
{
  "error": "Permission denied | Validation failed | ...",
  "detail": "Full description",
  "field_errors": {}
}
```
- Uses `raise ValidationError({"error": "msg", "invalid_ids": [...]})` or `NotFound({"error": "POC not found"})` (updated in views.py).
- 401/403: Auth/Permission (`IsAuthenticated` for list/retrieve, `IsAdminOrManager` for mutations, `IsAdmin` for destroy).
- 400: Validation (invalid status, serializer errors, duplicate email in import, missing required).
- Matches jobs.md pattern exactly. See `custom_exception_handler`.

**RBAC**: `get_permissions()` + role-scoped `get_queryset()` (ADMIN/MANAGER=full org clients; RECRUITER=clients with their assigned jobs via jobs__assigned_recruiters; none otherwise). `IsAdminOrManager` for create/update/poc/document/status. Mirrors `JobViewSet` and `CandidateViewSet`. Recruiters see limited list/detail.

## Flow Diagram - Client Onboarding to Jobs + Notifications/Emails

```mermaid
flowchart TD
    A[Admin/Manager] --> B[POST /api/v1/clients/ (JSON with nested pocs or multipart with agreement_document)]
    B --> C[Auto client_id=CLI-XXXX + perform_create log + auto agreement_document_name]
    C --> D[Add POCs via POST /clients/{id}/pocs/ or nested<br/>POCType=hiring/payment]
    D --> E[Upload general Docs via POST /clients/{id}/documents/ (multipart, auto file_name)]
    E --> F[PATCH /clients/{id}/ (for agreement update) or /status/<br/>Update commercials, notes, commercial_decided=true]
    F --> G[Client ACTIVE → Create Job (client FK)]
    G --> H[Candidate Pipeline: submit-to-client → simulate_client_submission_email<br/>using send_org_email(organization, to=poc.email, template='client_submission', context with branding)]
    H --> I[In-app Notification created for assigned recruiters (Notification model, org-scoped)]
    I --> J[POC receives branded email (org SMTP or fallback); resume_link, job details]
    J --> K[Feedback loop: update Application status, notifications/tasks.py updates]

    subgraph "New APIs & File Support"
    L[change_status, manage_poc, upload_document (with parsers), agreement_document on create]
    M[accounts/email_utils.py: get_org_email_connection(), send_org_email() with custom_html or template fallback]
    N[notifications/tasks.py uses org-aware sending + Notification.create()]
    end
    B --> L & M & N
```

## Key APIs

### ClientViewSet (/api/v1/clients/)
- **Auth/RBAC**: `get_permissions()` returns `IsAuthenticated()` for list/retrieve (recruiters see via job linkage), `IsAdmin()` for destroy, `IsAdminOrManager()` for all mutations (create, update, change_status, pocs, documents). `get_queryset()` filters by org + role.
- **List**: `GET /api/v1/clients/?status=active&industry=IT&city=Mumbai&search=tech&ordering=-created_at` — uses `ClientListSerializer` (flat fields). Full filtering via `ClientFilterSet` (status, industry~icontains, city/state/country~icontains, created_after/before, agreement_date_after, has_agreement, commercial_decided), `SearchFilter` (company_name, client_name, email, industry, city), `OrderingFilter` (company_name, status, created_at, updated_at, agreement_date). `DjangoFilterBackend` enabled.
  **Response (200)**: Paginated list.
  ```json
  {
    "count": 5,
    "results": [{
      "id": "uuid1",
      "client_id": "CLI-0001",
      "company_name": "Tech Corp Inc.",
      "industry": "IT Services",
      "status": "active",
      "email": "jane@techcorp.com",
      "contact": "9876543210",
      "city": "Mumbai",
      "open_jobs_count": 2,
      "created_by_name": "Manager One",
      "created_at": "2025-01-01T10:00:00Z"
    }]
  }
  ```
  Use detail for full (pocs grouped by type {hiring:[], payment:[]}, documents array, stats, agreement_document, all fields).

- **Create**: `POST /api/v1/clients/` (full body with **everything**; supports nested pocs + multipart for `agreement_document`).
  **Step-by-Step**:
  1. Auth as Admin/Manager.
  2. For JSON (no files): send full JSON body (min required + pocs). For files: use `multipart/form-data` (include `agreement_document` as file field, other fields as form fields; pocs as JSON-stringified if needed).
  3. `ClientDetailSerializer` + `create()` handles nested POCs, auto `agreement_document_name` from file, org/created_by via `perform_create`, logs.
  4. Returns full detail (201). General docs prefer post-create `/documents/` (now supports multipart + auto file_name).
  5. Auto `client_id=CLI-XXXX`.

  **Full Request Body Example (JSON - no file)** (takes **everything in body**):
  ```json
  {
    "company_name": "Tech Corp Inc.",
    "client_name": "Jane Smith",
    "email": "jane@techcorp.com",
    "alternative_email": "hr@techcorp.com",
    "contact": "9876543210",
    "alternative_contact": "9123456789",
    "website": "https://techcorp.com",
    "linkedin": "https://linkedin.com/company/techcorp",
    "street": "123 Tech Park, Andheri East",
    "city": "Mumbai",
    "state": "Maharashtra",
    "country": "India",
    "postal_code": "400093",
    "client_location": "Andheri",
    "industry": "IT Services",
    "gst_number": "27AAECT1234B1Z2",
    "status": "active",
    "agreement_date": "2025-01-15",
    "payment_period_days": 30,
    "replacement_period_days": 90,
    "commercial_decided": true,
    "notes": "Preferred vendor. High priority for Python roles.",
    "pocs": [
      {
        "poc_type": "hiring",
        "name": "Hiring Manager",
        "email": "hiring@techcorp.com",
        "designation": "Talent Acquisition Head",
        "contact": "9123456789",
        "linkedin": "https://linkedin.com/in/hiringmgr",
        "description": "Primary POC for candidate submissions"
      },
      {
        "poc_type": "payment",
        "name": "Finance POC",
        "email": "finance@techcorp.com",
        "designation": "Accounts Manager",
        "contact": "9988776655"
      }
    ],
    "documents": []
  }
  ```
  **For agreement doc on create**: Use multipart/form-data with `agreement_document` file + above fields (serializer auto-sets name). Response includes `agreement_document` (file URL/path), `agreement_document_name`.

  **Full Success Response (201)**: Full detail incl. `client_id`, `pocs: {hiring: [...], payment: [...] }`, `documents: []`, `agreement_document`, `stats: {...}`, `created_by: {UserBrief}`.

- **Retrieve/Update**: `GET/PATCH /api/v1/clients/{id}/` — full `ClientDetailSerializer` (all fields + computed). PATCH partial (ignores nested pocs/documents; use dedicated actions). `perform_update` logs.

- **Destroy**: `DELETE /api/v1/clients/{id}/` — soft-delete (`IsAdmin` only), logs.

- **Change Status (New API)**: `PATCH /api/v1/clients/{id}/status/`
  **Request Body** (full example):
  ```json
  {
    "status": "on-hold"
  }
  ```
  **Response (200)**:
  ```json
  {
    "status": "on-hold"
  }
  ```
  Validates against `ClientStatus.choices`; raises `ValidationError` on invalid (normalized). Logs with company_name. Mirrors `JobViewSet.change_status`.

### POC Management
- **Add POC**: `POST /api/v1/clients/{id}/pocs/` — body takes **all POC fields** (see table). Uses `POCSerializer`. Returns full data (201) or `ValidationError`.
  **Example Body**:
  ```json
  {
    "poc_type": "hiring",
    "name": "New Technical Recruiter",
    "email": "tech@client.com",
    "designation": "Sr. Recruiter",
    "contact": "555-1234",
    "linkedin": "https://linkedin.com/in/techrec",
    "description": "Handles technical interviews"
  }
  ```
  **Response**: Serialized POC (id, all fields, timestamps).

- **Manage POC**: `PATCH /api/v1/clients/{id}/pocs/{poc_id}/` or `DELETE /api/v1/clients/{id}/pocs/{poc_id}/`
  - PATCH: partial body with any fields; returns updated.
  - DELETE: soft-delete (204). Raises `NotFound` if not exists. Guards via client scoping.
  - Logs all actions.

### Document & Agreement Management
- **Upload General Document**: `POST /api/v1/clients/{id}/documents/` (**multipart/form-data** with `file` field; `file_name` auto-set if omitted). Now uses `parser_classes=[MultiPartParser, FormParser]`, `ClientDocumentSerializer`. Returns full doc (201) or `ValidationError`. Logs action.
- **Agreement Document**: Saved **separately** on `Client` model (`agreement_document` FileField). Upload during **create** (multipart) or via `PATCH /clients/{id}/` (updates name automatically in serializer). Preferred for main contract/agreement (separate from general `documents`).
- **Delete Document**: `DELETE /api/v1/clients/{id}/documents/{doc_id}/` — soft-delete (204) or `NotFound({"error": "Document not found"})`.

**Note on Nested vs Actions/Files**: 
- JSON create supports nested `pocs` (full objects) and `documents` (metadata).
- For **files on create**: Use multipart with `agreement_document` (auto-handled in `ClientDetailSerializer.create/update` + `parser_classes` on ViewSet). General docs: create client first, then use `/documents/` action (recommended for production file uploads).
- Matches candidate `upload_resume` pattern.

### Export Clients (CSV + Excel)
- **Endpoint**: `GET /api/v1/clients/export/?status=active&format=xlsx&template=1`
- **Auth**: `IsAuthenticated()` (all roles; QS mirrors `ClientViewSet.get_queryset()` **exactly** — ADMIN/MANAGER=full org, RECRUITER=clients via `jobs__assigned_recruiters` Q-filter, else none).
- Uses updated `ClientExportView` (`CLIENT_EXPORT_HEADERS` includes all: agreement_date, payment/replacement_period_days, commercial_decided=True in sample, agreement_document_name). Supports `?format=xlsx` (openpyxl, cleans bools like commercial_decided), `?template=1` (sample row with bool, no DB, filename with .xlsx, separate log).
- Optional `?status=` filter respected. Logs with count or template msg.
- **Response**: `generate_csv_response(..., export_format=...)` → `clients_export.{csv|xlsx}` or template.
- **TIP**: Use `/api/v1/export-formats/` or Export `?template=1&format=xlsx` for perfect import template (all fields, sample data). No file columns (agreement_document omitted; upload separately). Matches unified pattern across modules.

### Import Clients (Admin-only)
- **Endpoint**: `POST /api/v1/clients/import/`
- **Auth**: `IsAdmin()` (from `ClientImportView`; recruiters blocked).
- **Body**: multipart `file` (`.csv`/`.xlsx`/`.xls`).
- **Required** (per `CLIENT_IMPORT_REQUIRED`): `company_name, client_name, email, contact, industry` (normalized snake_case headers).
- **Step-by-Step**:
  1. Use template from Export `?template=1&format=xlsx` (includes sample with `commercial_decided=True`).
  2. `parse_csv_from_request` (Excel via openpyxl.data_only=True, header normalize, required validation).
  3. Per row (from 2, `transaction.atomic()`): dedup by `email__iexact+org`, `DateParserField` for agreement_date (fuzzy + format fallbacks), `get_choice()` for status (default ACTIVE), int parse for days, bool coercion (`str.lower() in ('true','1','yes')` for commercial_decided).
  4. Creates with `created_by=user`, `organization`. Skips dups with error.
  5. Returns 201 full or 207 partial + errors list (row-indexed).
- **Full Response** (201 or 207):
  ```json
  {
    "created": 3,
    "skipped": 1,
    "errors": [{"row": 4, "error": "Client with email 'dup@ex.com' already exists (org-scoped)."}]
  }
  ```

**TIP**: agreement_date flexible ("2025-01-15", "15/01/2025", "Jan 15 2025" etc. via `DateParserField`). commercial_decided accepts bool/string variants. Export first for template. Matches `ClientImportView`, `common/serializers.py`, `utils_csv.py:get_choice()`, audit with user. See field table for all (e.g. gst_number, notes).

## Integration Points
- **Jobs**: `client` FK (optional; `hiring_for=client` in Job). Recruiter QS uses jobs__assigned_recruiters. Import uses client lookup by name in jobs.
- **Candidates/Notifications**: On submission to client, `notifications/tasks.py` creates `Notification` (for recruiters) + `send_org_email(organization=client.organization, ...)` to POC.email (uses `OrganizationEmailConfig` or fallback, branding from `EmailTemplate`, context with candidate/job/client/resume_link). See `simulate_client_submission_email`.
- **Accounts/Email**: `send_org_email` injects org branding; POCs receive rich HTML (base_email.html + client_submission.html). Fernet encrypted SMTP creds per org.
- **Audit**: All (create/update/destroy/status/poc/document/export/import) call `log_action`.
- **Serializers**: `ClientDetailSerializer` special handling for nested + stats/pocs grouping. `UserBriefSerializer` for created_by.
- **URLs**: router for ViewSet + explicit /export/, /import/ from views_export.py.
- **Org Scoping**: All QS filtered; `unique_together` prevents duplicate client_ids per org.

**Common POC Types**: hiring (for submissions/interviews), payment (for invoices).

**Notes**:
- **Unified Export/Import**: All modules now support CSV+XLSX via `?format=xlsx` (openpyxl in `generate_csv_response` with data cleaning for bools/dates), `?template=1`, normalized parser (header snake_case, Excel data_only=True, row errors from 2, 201/207 contract, per-row atomic, `DateParserField`, `get_choice`). `ExportFormatsView` centralizes headers/required/URLs. Recruiter RBAC in export QS (via jobs link), admin-only for client import.
- **Upload docs on create + separate agreement**: Added `agreement_document`/`agreement_document_name` to `Client` (FileField like resume). Serializer handles multipart + auto-name. ViewSet parsers support both JSON/multipart.
- **Docs = source of truth**: Full tables, JSON examples, mermaid, RBAC Q-filter details, normalized error contract, Excel support notes. Verified 1:1 with live code (`clients/views_export.py` updated with template/format/RBAC mirroring ViewSet, `views.py` with get_permissions+QS, models, serializers, `common/utils_csv.py`, `common/serializers.py`, `audit/utils.py` (user=None), `docs/*.md` cross-refs, `common/permissions.py`, exceptions).
- Matches jobs/candidates (RBAC alignment, import patterns, public upload with user=None). `python manage.py check` clean. Ready for frontend testing (xlsx downloads, bulk imports with partial errors, template usage).

**Verification**: Synced with `jobs/views.py` (manage_recruiters full list + invalid_ids), `candidates/views.py` (MultiPartParser + resume handling), `notifications/tasks.py`, email_utils. Full end-to-end client create (with agreement/POCs) → job → submission email + Notification now supported.

