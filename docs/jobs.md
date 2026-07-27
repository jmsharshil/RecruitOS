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
| `client` | UUID (string) | No | Valid Client ID from org | null | Foreign key to Client (lookup by UUID) |
| `status` | string | No | "open", "closed", "on-hold" | "open" | Current job status |
| `assigned_recruiter_ids` | array[UUID] | No | Valid recruiter User IDs | [] | Write-only; assigns M2M recruiters (must be role=recruiter) |
| `target_closing_date` | string (date) | No | YYYY-MM-DD | null | Target date to close the req |
| `notice_period_preference` | string | No | - | "" | Preferred notice period (e.g. "30 days") |
| `skill_criteria` | decimal (0-100) | No | 0-100 | 70.00 | AI resume match threshold % |
| `code` | string | No (read-only) | JOB-000001 | auto | Auto-generated per org |
| `resume_upload_link` | string | No (read-only) | URL | auto | Generated link for public uploads |

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

## Flow Diagram - Job Creation to Pipeline Setup (with Application)

```mermaid
flowchart TD
    A[Client Created] --> B[Create Job<br/>POST /api/v1/jobs/]
    B --> C[Auto-create Default Stages<br/>Screening → HR Round → Technical → Client Round → Offer → Hired]
    C --> D[Assign Recruiters<br/>Many-to-Many]
    D --> E[Share Resume Upload Link (PublicUploadView)]
    E --> F[Add to Pool (Candidate) or Create Application (job-linked)]
    F --> G[Monitor Pipeline per Stage (via Application queryset)]
    G --> H[Update Job Status<br/>PATCH /jobs/{id}/status/]
    H --> I[Close Job when positions filled]
    
    subgraph Stages Management
    J[Add Custom Stage]
    K[Reorder Stages]
    L[Update Stage Color]
    end
    C --> J & K & L
```

## Key APIs

### JobViewSet (/api/v1/jobs/)
- **Auth**: Uses `get_permissions()` — `IsAuthenticated()` for list/retrieve/get_upload_link; `IsAdmin()` for destroy; `IsAdminOrManager()` for create/update/change_status/stages (mirrors CandidateViewSet/ApplicationViewSet). Role-scoped `get_queryset()` via UserRole (ADMIN=all org, MANAGER=created_by=self, RECRUITER=assigned_recruiters).
- **List**: `GET /api/v1/jobs/?status=open&client=uuid`
  - Role-based QS (`is_deleted=False`, org filter).
  - **Response (200)**: Paginated `JobSerializer` (includes nested stages, computed `candidate_count`, `client_name`, `assigned_recruiters` list, `resume_upload_link`).
    ```json
    {
      "count": 15,
      "results": [{
        "id": "job-uuid",
        "code": "JOB-0001",
        "title": "Senior Python Developer",
        "status": "open",
        "priority": "high",
        "openings": 3,
        "client_name": "Tech Corp",
        "assigned_recruiters": ["user-uuids"],
        "stages": [{"name": "Screening", "order": 1, "color": "slate"}, ...],
        "candidate_count": 5,
        "resume_upload_link": "https://frontend.app/upload/job-uuid-here"
      }]
    }
    ```

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
      {"id": "user-uuid-1", "email": "rec1@org.com", "full_name": "Recruiter One"}
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
    "created_by": {"id": "...", "email": "...", "full_name": "..."},
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

### Upload Link
- **GET /api/v1/jobs/{id}/upload-link/** (`@action(detail=True, methods=['get'])`)
  **Step-by-Step**:
  1. Any authenticated user (IsAuthenticated) who can see the job (per get_queryset RBAC).
  2. Call GET `/api/v1/jobs/{job_id}/upload-link/`.
  3. Returns the pre-generated link (from `Job.resume_upload_link`, set in `save()`).
  4. Frontend uses this link to allow candidates to upload resumes publicly (hits `candidates.PublicUploadView` with job_uuid param for scoping to org/job).
  5. Uploaded candidates go to pool or first stage of this job.

  **Full Response (200)**:
  ```json
  {
    "resume_upload_link": "https://frontend.app/upload/3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```
  - Link is unique per job. Can be regenerated if needed by updating job. Protected but publicly usable endpoint it points to is AllowAny.

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
- **Accounts**: `UserRole` + `common.permissions` (IsAdminOrManager, IsAdmin, IsAuthenticated in `get_permissions()`); `get_queryset()` role filters; M2M `assigned_recruiters` (limit to recruiters); `created_by` for Manager scoping + audit.
- **Clients**: Optional FK; import uses iexact lookup (warning only if missing); `hiring_for=client` gates send-to-client in applications.
- **Candidates/Application**: `PublicUploadView` (AllowAny, job_uuid scoped), `Application.current_stage` FK to Job.Stage, `move_stage` validates ownership, auto-first-stage from `DEFAULT_STAGES` on create/import (exact match between `perform_create` and `JobImportView`).
- **Audit/Logs**: Every mutation (`perform_*`, status, stages add/manage, export, import) calls `log_action(user, verb, model, id, note)`. Supports `user=None` for public uploads.
- **Shared Utils**: `common.utils_csv` for parse/generate, `common.exceptions.custom_exception_handler` (now handles ValidationError/NotFound uniformly with `{"error":..., "detail":..., "field_errors":...}`), `BaseModel`.
- **URLs**: `jobs/urls.py` includes router for ViewSet + explicit paths for `export/`, `import/`, `{id}/upload-link/`, `{id}/stages/...`.

**Common Stages** (`DEFAULT_STAGES`): 
- Screening (slate, order=1)
- HR Round (blue, 2)
- Technical (indigo, 3)
- Client Round (sky, 4)
- Offer (amber, 5)
- Hired (green, 6)

Auto-created on **every** Job create/import. Custom stages via API (order/color supported; cannot delete if has active applications).

**Notes**:
- **Docs == source of truth**: All contracts (JSON payloads, CSV headers/required, QS filters, error shapes with ValidationError/NotFound, 201/207, row-indexing, choice fallbacks, RBAC patterns, Mermaid) verified 1:1 against live code in `jobs/views*.py`, `models.py`, `serializers.py`, `urls.py`, `docs/candidates.md`.
- RBAC fully centralized (no more permission_classes on ViewSet; `get_permissions()` + `get_queryset()` with UserRole checks). Recruiters can list/retrieve assigned jobs but blocked from export/import/mutations.
- Import hardened with explicit title dedup (beyond model), safe Decimal, case-insens choice matching, per-row atomic tx + stages, client warning (non-fatal), broad except for robustness.
- Export aligned with CandidateExportView (permission change, QS comment, isinstance for skills).
- All views now consistently `raise ValidationError(...)` or `NotFound` for errors (no raw Response(..., status=4xx) except serializer in some legacy paths now updated).
- `python manage.py check` passes; seed data, dashboards updated in accounts/candidates for consistency.
- Ready for frontend: exact match on all endpoints, auth, error formats, CSV templates, pipeline actions. Test import/export flows + RBAC (admin/manager vs recruiter).

**Verification**: Synced with `candidates/views_export.py` (mirrored structure), `common/permissions.py`, updated dashboards in `accounts/views.py`, `candidates/views.py`. Full audit trail + soft-delete everywhere.

