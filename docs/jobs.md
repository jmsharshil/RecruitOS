# Jobs Module Documentation

## Overview
Manages job requisitions/positions. Linked to clients (FK), assigned_recruiters (M2M), multi-stage pipeline (Stage FK on Application). All models inherit `BaseModel` for org-scoping + soft-delete.

**Key Models**: Job (UUID PK, JSONField skills, Decimal budget, auto code/resume_upload_link in save), Stage

**Choice Enums** (in models.py):
- `JobStatus`: "open", "closed", "on-hold" (default: "open")
- `Priority`: "high", "medium", "low" (default: "medium")
- `JobTypes`: "permanent", "contractual" (default: "permanent")
- `JobModes`: "remote", "hybrid", "office" (default: "office")
- `HiringFor`: "self", "client" (default: "self")

All choice fields in API/import use case-insensitive matching via `get_choice()` helper (matches on value or label, falls back to default). See `common/utils_csv.py`.

**Job Fields Reference** (all fields from JobSerializer + model)

Use this table to understand **required** vs **optional**, types, choices, and defaults for request bodies.

| Field Name | Type | Required for Create? | Choices / Format | Default | Description / Notes |
|------------|------|-----------------------|------------------|---------|---------------------|
| `title` | string | **Yes** | - | - | Job title (used for dedup in import) |
| `description` | text | **Yes** | - | - | Detailed job description |
| `skills` | array[string] | No | e.g. ["Python", "Django"] | [] | List of required skills (JSON in model) |
| `education` | string | No | - | "" | Required qualification (e.g. "B.Tech CSE") |
| `min_experience` | integer | **Yes** (esp. import) | >= 0 | 0 | Minimum years of experience |
| `max_experience` | integer | **Yes** (esp. import) | >= 0 | 0 | Maximum years of experience |
| `location` | string | **Yes** | - | - | Job location/city (e.g. "Remote", "Bangalore") |
| `openings` | integer | No | > 0 | 1 | Number of positions |
| `priority` | string | No | "high", "medium", "low" | "medium" | Priority level |
| `budget` | number (decimal) | No | >= 0 | 0 | Budget/CTC in rupees (e.g. 1500000.00) |
| `job_type` | string | No | "permanent", "contractual" | "permanent" | Type of employment |
| `job_mode` | string | No | "remote", "hybrid", "office" | "office" | Work arrangement |
| `hiring_for` | string | No | "self", "client" | "self" | Whether hiring for internal or client |
| `client` | UUID (string) | No | Valid Client ID from org (see docs/clients.md for full Client/POC fields + change_status API) | null | FK to Client; enables send-to-client flow + POC emails/notifications. Use nested or lookup by company_name in import. |
| `status` | string | No | "open", "closed", "on-hold" | "open" | Current job status (use /status/ action) |
| `assigned_recruiter_ids` | array[UUID] | No | Valid recruiter User IDs | [] | Write-only in create; full list semantics also via dedicated /recruiters/ endpoint (see below) |
| `target_closing_date` | string (date) | No | YYYY-MM-DD | null | Target date to close the req |
| `notice_period_preference` | string | No | - | "" | Preferred notice period (e.g. "30 days") |
| `skill_criteria` | decimal (0-100) | No | 0-100 | 70.00 | AI resume match threshold % |
| `code` | string | No (read-only) | JOB-000001 | auto | Auto-generated per org |
| `resume_upload_link` | string | No (read-only) | URL | auto | Generated link for public uploads (used in candidate email context) |

**Notes on Fields**:
- **Required in Import CSV/Excel**: `title`, `min_experience`, `max_experience`, `location` (validated in `parse_csv_from_request` + per-row check).
- Other fields like `client_name` (for import only, string lookup by company_name__iexact), `skills` (comma-separated in CSV).
- All mutations log via `audit.log_action`.
- Read-only fields ignored in POST/PATCH.

**Error Handling (All Endpoints)**
All errors normalized by `common.exceptions.custom_exception_handler` (in settings.py) into:
```json
{
  "error": "Permission denied | Validation failed | ...",
  "detail": "Full description (e.g. 'Cannot delete stage with candidates')",
  "field_errors": {}
}
```
- Uses `raise ValidationError({"error": "msg"})` or `NotFound` in views (triggers handler).
- **401/403**: Auth/Permission (IsAuthenticated, IsAdminOrManager, IsAdmin).
- **400**: Validation (invalid status, missing title, stage with candidates, parse errors).
- Matches all examples. See `common/exceptions.py`.

**RBAC**: Centralized in `common.permissions` + `get_permissions()` + role-scoped `get_queryset()` (Q not needed for Jobs; uses if-elif on UserRole.ADMIN/MANAGER/RECRUITER). `IsAdminOrManager` for mutations/export/import, `IsAdmin` for destroy, `IsAuthenticated` for reads/upload-link. Recruiters blocked from job export/import (but allowed for candidates).

## Flow Diagram - Job Creation to Pipeline Setup (with Application + Client/POC/Email Integration)

```mermaid
flowchart TD
    A[Client Created (docs/clients.md)<br/>with POCs + change_status] --> B[Create Job<br/>POST /api/v1/jobs/ (full body)]
    B --> C[Auto-create 6 DEFAULT_STAGES + code= JOB-XXXX + resume_upload_link<br/>in Job.save() + perform_create + audit]
    C --> D[Assign Recruiters via POST /jobs/{id}/recruiters/<br/>full {"recruiter_ids": [...] } list → .set() after validation]
    D --> E[GET /jobs/{id}/upload-link/ → Public talent pool upload]
    E --> F[Candidate created (pool) → Application (auto first stage)]
    F --> G[Pipeline: move_stage, schedule_interview (reminder email), send-to-client]
    G --> H[send_org_email(organization, to=POC.email, template='client_submission', full context + branding)<br/>+ create Notification (in-app for recruiters)]
    H --> I[Client feedback → update status, hired syncs job status]
    I --> J[Update Job Status<br/>PATCH /jobs/{id}/status/ or close when filled]
    
    subgraph "Stages + Recruiter Mgmt"
    K[POST /jobs/{id}/stages/ (add)]
    L[PATCH/DELETE /jobs/{id}/stages/{sid}/ (guard on candidates)]
    M[manage_recruiters (full list, invalid_ids error, UserBrief response)]
    end
    C --> K & L & M
    A --> H
```

## Key APIs

### JobViewSet (/api/v1/jobs/)
- **Auth**: Uses `get_permissions()` — `IsAuthenticated()` for list/retrieve/get_upload_link; `IsAdmin()` for destroy; `IsAdminOrManager()` for create/update/change_status/stages/manage_recruiters (mirrors CandidateViewSet/ApplicationViewSet). Role-scoped `get_queryset()` via UserRole (ADMIN=all org, MANAGER=created_by=self, RECRUITER=assigned_recruiters).
- **List**: `GET /api/v1/jobs/?status=open&client=uuid&search=python&priority=high`
  - Uses `JobListSerializer` (flat, performant for lists; no nested). 
  - Role-based `get_queryset()` via `UserRole`: ADMIN=full org, MANAGER=own created jobs, RECRUITER=assigned_jobs only. All filter `is_deleted=False`.
  - Supports `DjangoFilterBackend` (`JobFilterSet`: status, priority, job_mode, job_type, hiring_for, client=uuid, min_exp, max_exp, location__icontains, closing_after/before, created_after/before), `SearchFilter` (title,description,location,code), `OrderingFilter`.
  - Computed: `client_name` (from client.company_name), `candidate_count`, `created_by_name`.
  - **Response (200)**: Paginated `JobListSerializer`.
    ```json
    {
      "count": 15,
      "next": null,
      "previous": null,
      "results": [{
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "code": "JOB-000001",
        "title": "Senior Python Developer",
        "status": "open",
        "priority": "high",
        "job_mode": "remote",
        "job_type": "permanent",
        "location": "Remote",
        "openings": 3,
        "min_experience": 5,
        "max_experience": 8,
        "hiring_for": "self",
        "client_name": "Tech Corp",
        "candidate_count": 5,
        "target_closing_date": "2025-06-30",
        "created_by_name": "Manager One",
        "created_at": "2025-01-01T10:00:00Z"
      }]
    }
    ```
    For full details (stages array via `get_stages()`, `assigned_recruiters` as UserBrief[], `resume_upload_link`, `description`, `skills`, `created_by` object, etc.) use `GET /api/v1/jobs/{id}/` which uses `JobDetailSerializer`.

- **Create**: `POST /api/v1/jobs/`
  **Step-by-Step Guide**:
  1. Authenticate as **Admin** or **Manager** (IsAdminOrManager permission).
  2. (Optional) Ensure target `Client` exists via Clients API and note its `id`.
  3. Prepare full request body (see below). At minimum provide all **Yes** fields from the Job Fields Reference table.
  4. POST to `/api/v1/jobs/`. The `perform_create` will:
     - Set `created_by`, `organization`.
     - Auto-generate `code` (e.g. "JOB-000001") and `resume_upload_link`.
     - Create 6 default stages (Screening to Hired).
     - Log the action in audit trail.
  5. On success, use the returned `id`, `code`, `resume_upload_link`, and `stages`.
  6. (Optional) Assign more recruiters or update stages later.
  7. Share `resume_upload_link` with candidates (points to PublicUploadView).

  **Full Request Body Example** (all fields shown; **bold** = required for typical create; choices shown where applicable):
  ```json
  {
    "title": "Senior Python Developer",                  // **required**
    "description": "Build scalable backend services using Django, REST APIs, and PostgreSQL. Experience with cloud (AWS/Azure) is a plus.",  // **required**
    "skills": ["Python", "Django", "REST", "PostgreSQL", "AWS"],  // optional, array
    "education": "B.Tech in Computer Science or equivalent",  // optional
    "min_experience": 5,                                 // **required** (for import too)
    "max_experience": 8,                                 // **required** (for import too)
    "location": "Remote",                                // **required**
    "openings": 3,                                       // optional, default=1
    "priority": "high",                                  // optional; choices: "high", "medium", "low"
    "budget": 1800000.00,                                // optional; Decimal e.g. for CTC in INR
    "job_type": "permanent",                             // optional; choices: "permanent", "contractual"
    "job_mode": "remote",                                // optional; choices: "remote", "hybrid", "office"
    "hiring_for": "self",                                // optional; choices: "self", "client"
    "client": "3fa85f64-5717-4562-b3fc-2c963f66afa6",   // optional; UUID of Client (null if hiring_for=self)
    "status": "open",                                    // optional; choices: "open", "closed", "on-hold"
    "assigned_recruiter_ids": ["user-uuid-1", "user-uuid-2"],  // optional; array of recruiter User UUIDs
    "target_closing_date": "2025-06-30",                 // optional; ISO date string
    "notice_period_preference": "30 days",               // optional
    "skill_criteria": 75.0                               // optional; 0-100 for AI parsing
  }
  ```
  **Full Success Response (201 Created)**:
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "title": "Senior Python Developer",
    "description": "...",
    "code": "JOB-000001",
    "skills": ["Python", "Django", "REST", "PostgreSQL", "AWS"],
    "education": "B.Tech in Computer Science or equivalent",
    "min_experience": 5,
    "max_experience": 8,
    "location": "Remote",
    "openings": 3,
    "priority": "high",
    "budget": "1800000.00",
    "job_type": "permanent",
    "job_mode": "remote",
    "hiring_for": "self",
    "client": "client-uuid-here",
    "client_name": "Tech Corp",
    "status": "open",
    "assigned_recruiters": [
      {"id": "user-uuid-1", "name": "Recruiter One", "email": "rec1@org.com", "role": "recruiter"}
    ],
    "stages": [
      {"id": "stage-1", "name": "Screening", "order": 1, "color": "slate"},
      {"id": "stage-2", "name": "HR Round", "order": 2, "color": "blue"},
      {"id": "stage-3", "name": "Technical", "order": 3, "color": "indigo"},
      {"id": "stage-4", "name": "Client Round", "order": 4, "color": "sky"},
      {"id": "stage-5", "name": "Offer", "order": 5, "color": "amber"},
      {"id": "stage-6", "name": "Hired", "order": 6, "color": "green"}
    ],
    "candidate_count": 0,
    "resume_upload_link": "https://frontend.app/upload/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "created_by": {"id": "...", "name": "Manager One", "email": "...", "role": "manager"},
    "created_at": "2025-01-01T10:00:00Z",
    "target_closing_date": "2025-06-30",
    "notice_period_preference": "30 days",
    "skill_criteria": "75.00"
  }
  ```
  **Error Examples** (normalized by custom_exception_handler):
  - 400: `{"error": "Validation failed", "detail": "...", "field_errors": {"title": ["This field is required."]}}`
  - Invalid choice: Handled by serializer or `get_choice()` fallback.

- **Retrieve/Update**: `GET/PATCH /api/v1/jobs/{id}/` — full details or partial (skills list, M2M recruiters, budget as Decimal, etc.). `perform_update` logs.

- **Destroy**: `DELETE /api/v1/jobs/{id}/` — soft-delete only (`IsAdmin`).

- **Change Status**: `PATCH /api/v1/jobs/{id}/status/`
  **Step-by-Step**:
  1. GET the job to confirm current status and ID (use list/retrieve).
  2. Prepare body with valid `status` (see choices below).
  3. PATCH `/api/v1/jobs/{job_id}/status/`.
  4. ViewSet validates against `JobStatus.choices`; if invalid, raises `ValidationError` → normalized 400 error.
  5. On success, updates model, calls `log_action`, returns new status.
  6. Note: Closing a job (status="closed") prevents new applications in pipeline.

  **Request Body** (full; only status field needed):
  ```json
  {
    "status": "closed"   // Required; must be one of: "open", "closed", "on-hold"
  }
  ```
  **Full Success Response (200)**:
  ```json
  {
    "status": "closed"
  }
  ```
  **Possible Choice Values for `status`**:
  - `"open"` - Actively hiring
  - `"closed"` - Position filled or cancelled
  - `"on-hold"` - Temporarily paused

  **Error Example (400)**:
  ```json
  {
    "error": "Invalid status",
    "detail": "Invalid status",
    "field_errors": {}
  }
  ```

### Stages Management (JobViewSet actions)
**Note on Stages**: Every Job auto-creates 6 `DEFAULT_STAGES` on create/import (see table in reference). Custom stages can be added. `color` is free-form (common: "slate", "blue", "indigo", "sky", "amber", "green", "red", "purple"). Order determines pipeline sequence. Cannot delete stage if it has active (non-deleted) Applications.

- **Add Stage**: `POST /api/v1/jobs/{id}/stages/` (`@action(detail=True, methods=['post'])`)
  **Step-by-Step**:
  1. Retrieve job to get its `id`.
  2. Choose unique `name`, appropriate `order` (to insert in sequence), and `color`.
  3. POST to `/api/v1/jobs/{job_id}/stages/`.
  4. Serializer validates, creates with org/job scoping, logs action.
  5. Returns full stage; job's nested stages in future GETs will include it.

  **Full Request Body**:
  ```json
  {
    "name": "Final Interview",     // required
    "order": 7,                    // required for sorting; integer
    "color": "emerald"             // optional; any tailwind-like color name/string
  }
  ```
  **Full Response (201)**:
  ```json
  {
    "id": "stage-uuid-here",
    "name": "Final Interview",
    "order": 7,
    "color": "emerald"
  }
  ```

- **Manage Stage**: `PATCH /api/v1/jobs/{id}/stages/{stage_id}/` or `DELETE /api/v1/jobs/{id}/stages/{stage_id}/`
  **Step-by-Step for PATCH**:
  1. Use job_id and stage_id (from job retrieve or list).
  2. PATCH with partial fields (e.g. only change color or name).
  3. Returns updated stage (200).

  **Step-by-Step for DELETE**:
  1. Check if stage has candidates (via pipeline).
  2. If yes, cannot delete (400 error).
  3. DELETE → soft delete (is_deleted=True, sets deleted_at), logs, returns 204.

  **PATCH Request Body Example**:
  ```json
  {
    "name": "Updated Technical Round",
    "color": "violet",
    "order": 3
  }
  ```
  **PATCH Success Response (200)**: Same as add stage response (updated values).
  
  **DELETE Success**: 204 No Content.
  
  **Common Errors**:
  - 404: `{"error": "Stage not found", "detail": "Stage not found", "field_errors": {}}`
  - 400 (has candidates): `{"error": "Cannot delete stage with candidates", "detail": "...", "field_errors": {}}`

**Stage Fields** (from StageSerializer): `id`, `name` (req), `order` (req for sort), `color` (default "indigo"). Nested in Job responses via `StageBriefSerializer` (id, name, color only).

### Recruiter Management
**Bulk set of assigned recruiters** (`@action(detail=True, methods=['post'], url_path='recruiters')` named `manage_recruiters`).

- **Endpoint**: `POST /api/v1/jobs/{job_id}/recruiters/`
- **Method**: POST only. Body must contain `{"recruiter_ids": ["uuid1", "uuid2", ...]}` (complete desired list of recruiter User UUIDs **every time**).
  - Initial assign: `["1", "2", "3"]`
  - Add more (4,5): `["1", "2", "3", "4", "5"]`
  - Unassign (e.g. remove 4): `["1", "2", "3", "5"]` (or empty `[]` to clear all)
- **Behavior**: Fully replaces M2M `assigned_recruiters.set(valid_recruiters)` (no incremental add/remove). Validates **all** IDs are active `role=RECRUITER` in same org (returns specific `invalid_ids` on error). Handles duplicates gracefully.
- **Auth/Permissions**: `IsAdminOrManager()` (recruiters cannot manage assignments). Uses `get_object()` for org scoping + RBAC.
- **Response (200)**:
  ```json
  {
    "status": "updated",
    "assigned_recruiters": [
      {"id": "uuid1", "name": "Recruiter One", "email": "r1@org.com", "role": "recruiter", ...},
      ...
    ]
  }
  ```
  (Uses `UserBriefSerializer(many=True)`; empty list on clear.)
- **Logging**: `log_action(..., 'updated' or 'unassigned', 'Job', job.id, note_with_count_and_ids)`
- **Errors** (normalized 400):
  - Bad input: `{"error": "recruiter_ids must be a list", ...}`
  - Invalid IDs: `{"error": "Some recruiter IDs are invalid...", "invalid_ids": ["bad-uuid"]}`
- **Notes**: Complements writable `assigned_recruiter_ids` (in `JobDetailSerializer` for create/PATCH of whole Job). Affects recruiter `get_queryset()` (only see assigned jobs), notifications (`candidates/tasks.py`), dashboards, and detail responses. Matches exact user requirement for full-list semantics on every call. No per-ID URL param or DELETE method. Updated in `get_permissions()`, view action, and this doc.

### Upload Link
- **GET /api/v1/jobs/{id}/upload-link/** (`@action(detail=True, methods=['get'])` in JobViewSet)
  **Step-by-Step**:
  1. Any authenticated user (`IsAuthenticated()`) who can see the job per RBAC `get_queryset()`.
  2. GET `/api/v1/jobs/{job_id}/upload-link/`.
  3. If `resume_upload_link` not set (legacy), calls `job.save()` to generate it (uses `http://localhost:5173/upload/{job.id}` or configured frontend domain).
  4. Returns the link. Frontend route `/upload/{job-id}` uses `TalentPoolPublicUploadView` (AllowAny, at `/api/v1/candidates/public-upload/`) — now decoupled to shared talent pool (no direct job_uuid in backend; recruiters later create `Application` to link to job/stage).
  5. Public uploads log with `user=None`, trigger notification, support AI parse fallback.

  **Full Response (200)**:
  ```json
  {
    "resume_upload_link": "http://localhost:5173/upload/3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```
  - Link generated in `Job.save()` (robust, org-scoped). Frontend compatibility: public upload now lands in talent pool; use Application API to move to specific job's first stage (auto-set in `perform_create`).

### Export Jobs (CSV) - Matches JobExportView
- **Endpoint**: `GET /api/v1/jobs/export/?status=open`
- **Auth**: `permission_classes = [IsAdminOrManager]` (blocks recruiters; uses `UserRole` inside for MANAGER filter).
- **QS**: `select_related('client')`, `is_deleted=False`, org-scoped; if MANAGER then `created_by=user`.
- **Query**: Optional `?status=...` (exact match on Job.status).
- **Logic**: Builds rows; `client.company_name if j.client else ''`, `', '.join(...) if isinstance(j.skills, list) else ...`, `float(j.budget or 0)`.
- **CSV Headers** (`JOB_EXPORT_HEADERS`): `title,min_experience,max_experience,location,openings,priority,job_type,job_mode,hiring_for,client_name,status,skills,education,budget,description`
- **Response**: `generate_csv_response('jobs_export.csv', JOB_EXPORT_HEADERS, rows)`
- **Audit**: `log_action(request.user, 'exported', 'Job', None, f"Exported {len(rows)} jobs")`. Matches updated `CandidateExportView`.

### Import Jobs (CSV or Excel) - Matches JobImportView
- **Endpoint**: `POST /api/v1/jobs/import/`
- **Auth**: `IsAdminOrManager()` (recruiters blocked). Uses `MultiPartParser`.
- **Body**: multipart/form-data with `file` (supports `.csv`, `.xlsx`, `.xls` via updated `parse_csv_from_request` in `common/utils_csv.py` which normalizes headers to snake_case).
- **Required Fields** (from `JOB_IMPORT_REQUIRED` + per-row): `title`, `min_experience`, `max_experience`, `location`. Others optional (see Job Fields Reference table).
- **Supported Columns** (match export headers; normalized): `title`, `description`, `min_experience`, `max_experience`, `location`, `openings`, `priority` (choices: high/medium/low), `job_type` (permanent/contractual), `job_mode` (remote/hybrid/office), `hiring_for` (self/client), `client_name` (for lookup), `status` (open/closed/on-hold), `skills` (comma-separated), `education`, `budget`.

**Step-by-Step for Import**:
1. Call **Export** (`GET /api/v1/jobs/export/`) first to get a perfect template CSV/Excel with all headers and example data.
2. Populate your file: Use full choice values from reference table (or any case variation - `get_choice()` is forgiving). Row 1 = headers, data from row 2.
3. Upload via POST `/api/v1/jobs/import/` (multipart file field).
4. Backend: parses (Excel uses openpyxl with data_only=True, skips empty rows), validates required fields, normalizes headers via regex snake_case.
5. Per-row (row numbers start at 2 for Excel/CSV user errors):
   - Explicit title check + deduplication against existing jobs in org.
   - Optional client lookup via `client_name__iexact`.
   - Skills split by comma.
   - Safe parsing: int for experiences/openings, Decimal for budget (strips commas), `get_choice()` for all enums with model defaults.
   - Atomic transaction: create Job (triggers save() for code/link/stages) + create all 6 DEFAULT_STAGES.
   - Any error (dup, parse fail, exception) → add to errors list with row number, mark as skipped.
6. Audit log records created/skipped count.
7. Check response for errors even if some succeeded.

**Full Response Examples**:
- **All Successful (201 Created)**:
  ```json
  {
    "created": 10,
    "skipped": 0,
    "errors": []
  }
  ```
- **Partial Success (207 Multi-Status)**:
  ```json
  {
    "created": 7,
    "skipped": 3,
    "errors": [
      {"row": 3, "error": "Job with title 'Senior Python Developer' already exists."},
      {"row": 5, "error": "Client 'Unknown Inc' not found. Job will be created without a client."},
      {"row": 8, "error": "'abc' is not a valid integer for min_experience"}
    ]
  }
  ```

**Early Parse Error (400)**:
```json
{
  "error": "Missing required fields: title, min_experience, max_experience, location",
  "detail": "Missing required fields: title, min_experience, max_experience, location",
  "field_errors": {}
}
```

> [!TIP]
> **Export first** for exact header template (includes `client_name`, all fields). Import now fully supports Excel (.xlsx/.xls) + CSV. Tolerant of partial failures (client lookup warnings non-fatal). Errors are row-indexed starting at 2. All choice fields use case-insensitive `get_choice()` with documented fallbacks. Matches `JobImportView`, `parse_csv_from_request()`, and candidate import pattern. Test with mixed success cases for robustness. See updated `jobs/views_export.py` and `common/utils_csv.py`.

## End-to-End Job + Pipeline Flow (Mermaid updated to match code)

See top of file. Pipeline lives in `candidates` module (Application joins Candidate+Job+Stage; status on Application syncs with "Hired" stage).

## Key Integration Points
- **Accounts**: `UserRole` + `common.permissions` (IsAdminOrManager, IsAdmin, IsAuthenticated in `get_permissions()`); `get_queryset()` role filters; M2M `assigned_recruiters` (limit to recruiters via `User.objects.filter(role=RECRUITER...)` in manage_recruiters); `created_by` for Manager scoping + audit. `UserBriefSerializer` for recruiter responses.
- **Clients**: Optional FK to full Client model (see **docs/clients.md** for exhaustive fields table, nested POC create, change_status API, POCType, ClientDocument, org-aware emails to POCs). Import uses client_name lookup (warning on miss); `hiring_for=client` + POC.email gates `send_org_email` + `Notification` creation in `candidates/views.py` and `notifications/tasks.py`.
- **Candidates/Application**: `PublicUploadView` (AllowAny, resolves org), `Application` joins Candidate+Job+Stage, `move_stage`, `schedule_interview`, `send_to_client` (creates ClientSubmission, triggers org email + in-app notif). Auto-first-stage from `DEFAULT_STAGES`.
- **Notifications & Email**: Full org-aware stack (`OrganizationEmailConfig` with encrypted SMTP, `EmailTemplate` per-org, `send_org_email()` with branding/context/custom_html fallback to templates/emails/*.html). Used in client submission, interview reminders (to assigned_recruiters), resume notifications. Tasks wrapped in `@run_in_thread`.
- **Audit/Logs**: Every mutation (`perform_*`, status, stages, **manage_recruiters**, export, import, client actions) calls `log_action`. Supports full context in notes (e.g. recruiter IDs, invalid_ids).
- **Shared Utils**: `common.utils_csv`, `common.exceptions.custom_exception_handler` (normalizes ValidationError with "invalid_ids", NotFound), `BaseModel`, Fernet encryption in email_utils.
- **URLs**: router + explicit for export/import/upload-link/stages/recruiters.

**Common Stages** (`DEFAULT_STAGES`): 
- Screening (slate, order=1)
- HR Round (blue, 2)
- Technical (indigo, 3)
- Client Round (sky, 4)
- Offer (amber, 5)
- Hired (green, 6)

Auto-created on every Job. Custom via API (cannot delete with candidates).

**Notes**:
- **Docs == source of truth**: Updated to sync with clients.md (full client/POC integration, org-email, notifications). All JSON bodies take "everything in body" (full fields + recruiter_ids list), responses use UserBriefSerializer for recruiters, normalized errors with invalid_ids for manage_recruiters. Verified 1:1 with live code in `jobs/views.py` (updated manage_recruiters with full validation/.set()/audit), `clients/views.py` (new change_status + consistent raises), models, serializers, `accounts/email_utils.py`, `notifications/tasks.py`, `docs/clients.md`.
- RBAC centralized in `get_permissions()` + role QS (ADMIN full, MANAGER own, RECRUITER assigned). `manage_recruiters` restricted to IsAdminOrManager.
- Import/export hardened; client submissions now fully org-email aware with branding.
- `python manage.py check` passes. All QS org-filtered. Ready for testing/frontend (use full bodies, /recruiters/ for M2M, /clients/{id}/status/ for lifecycle, POC emails auto-triggered).

**Verification**: Matches prior work on Client/POC/Notification models, recruiter bulk-set, org-email encryption+fallback (console in DEBUG), custom_exception_handler. Full end-to-end from client create → job → candidate → POC email + in-app Notification.

