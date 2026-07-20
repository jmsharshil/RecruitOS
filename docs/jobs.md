# Jobs Module Documentation

## Overview
Manages job requisitions/positions. Linked to clients (FK), assigned_recruiters (M2M), multi-stage pipeline (Stage FK on Application). All models inherit `BaseModel` for org-scoping + soft-delete.

**Key Models**: Job (UUID PK, JSONField skills, Decimal budget, auto code/resume_upload_link in save), Stage

**Choice Enums** (in models.py): JobStatus (open/closed/on-hold), Priority (high/medium/low), JobTypes (permanent/contractual), JobModes (remote/hybrid/office), HiringFor (self/client). Used with case-insensitive `_get_choice()` helper in import.

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

**RBAC**: Centralized in `common.permissions` + `get_permissions()` + role-scoped `get_queryset()` (Q not needed for Jobs; uses if-elif on UserRole.ADMIN/MANAGER/RECRUITER). `IsAdminOrManager` for mutations/export/import, `IsAdmin` for destroy, `IsAuthenticated` for reads/upload-link. Recruiters blocked from export/import.

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
  **Request Body** (matches serializer + assigned_recruiter_ids for M2M):
  ```json
  {
    "title": "Senior Python Developer",
    "description": "Build scalable backend services...",
    "skills": ["Python", "Django", "REST", "PostgreSQL"],
    "min_experience": 5,
    "max_experience": 8,
    "location": "Remote",
    "openings": 2,
    "priority": "high",
    "job_type": "permanent",
    "job_mode": "remote",
    "hiring_for": "self",
    "client": "client-uuid",
    "budget": 1500000,
    "education": "B.Tech",
    "assigned_recruiter_ids": ["rec-uuid1", "rec-uuid2"]
  }
  ```
  **Response (201)**: Full Job + auto `perform_create` (sets code, resume_upload_link via model save, creates 6 DEFAULT_STAGES, log_action).

- **Retrieve/Update**: `GET/PATCH /api/v1/jobs/{id}/` — full details or partial (skills list, M2M recruiters, budget as Decimal, etc.). `perform_update` logs.

- **Destroy**: `DELETE /api/v1/jobs/{id}/` — soft-delete only (`IsAdmin`).

- **Change Status**: `PATCH /api/v1/jobs/{id}/status/`
  **Request Body**:
  ```json
  {
    "status": "closed"
  }
  ```
  **Response (200)**: `{"status": "closed"}`
  - Validates against JobStatus.choices; else `raise ValidationError({"error": "Invalid status"})` (normalized to 400).
  - Logs via `log_action`.

### Stages Management (JobViewSet actions)
- **Add Stage**: `POST /api/v1/jobs/{id}/stages/` (`@action`)
  **Body**:
  ```json
  {
    "name": "Final Interview",
    "order": 5,
    "color": "green"
  }
  ```
  **Response (201)**: Stage object. Uses `StageSerializer`, `log_action`.

- **Manage Stage**: `PATCH/DELETE /api/v1/jobs/{id}/stages/{stage_pk}/`
  - **PATCH**: Partial update (name/color/order). Returns updated serializer data (200).
  - **DELETE**: Soft-delete (`is_deleted=True`). 
    - If `stage.applications.filter(is_deleted=False).exists()`: `raise ValidationError({"error": "Cannot delete stage with candidates"})` (400).
    - Else 204 No Content, `log_action`.
  - Uses `try: Stage.objects.get(...) except: raise NotFound({"error": "Stage not found"})`.
  - `StageBriefSerializer` used in Job list/retrieve responses (nested stages).

**Note**: Matches `DEFAULT_STAGES` list in models (6 stages with colors). Custom stages allowed. Order used for sorting.

### Upload Link
- **GET /api/v1/jobs/{id}/upload-link/** (`@action`)
  - Protected by `IsAuthenticated`.
  - **Response (200)**:
    ```json
    {
      "resume_upload_link": "https://frontend.app/upload/{job-uuid}"
    }
    ```
  - Link generated in `Job.save()` (or updated); points to frontend that calls `PublicUploadView` (in candidates, with job_uuid for scoping, AllowAny).

### Export Jobs (CSV) - Matches JobExportView
- **Endpoint**: `GET /api/v1/jobs/export/?status=open`
- **Auth**: `permission_classes = [IsAdminOrManager]` (blocks recruiters; uses `UserRole` inside for MANAGER filter).
- **QS**: `select_related('client')`, `is_deleted=False`, org-scoped; if MANAGER then `created_by=user`.
- **Query**: Optional `?status=...` (exact match on Job.status).
- **Logic**: Builds rows; `client.company_name if j.client else ''`, `', '.join(...) if isinstance(j.skills, list) else ...`, `float(j.budget or 0)`.
- **CSV Headers** (`JOB_EXPORT_HEADERS`): `title,min_experience,max_experience,location,openings,priority,job_type,job_mode,hiring_for,client_name,status,skills,education,budget,description`
- **Response**: `generate_csv_response('jobs_export.csv', JOB_EXPORT_HEADERS, rows)`
- **Audit**: `log_action(request.user, 'exported', 'Job', None, f"Exported {len(rows)} jobs")`. Matches updated `CandidateExportView`.

### Import Jobs (CSV) - Matches JobImportView
- **Endpoint**: `POST /api/v1/jobs/import/`
- **Auth**: `IsAdminOrManager`, `parser_classes=[MultiPartParser, FormParser]`.
- **Body**: multipart `file` CSV.
- **Required**: `JOB_IMPORT_REQUIRED = ['title', 'min_experience', 'max_experience', 'location']` (validated by `parse_csv_from_request` → `raise ValidationError` on fail).
- **Per-row Logic** (enumerate(rows, start=2) for 1-based errors):
  - Title required + explicit dedup (`title__iexact + org + is_deleted=False`); skip+error if duplicate.
  - Client: optional `company_name__iexact` lookup (org-scoped); if not found, append warning to errors[] but continue with client=None.
  - Skills: split by comma + trim.
  - Parsing: int() defaults for exp/openings; `Decimal(str(budget_raw).replace(',','') or 0)`; `_get_choice(val, choices, default)` (case-insens on value/label, falls back to model defaults: OPEN/MEDIUM/PERMANENT/OFFICE/SELF).
  - `with transaction.atomic(): Job.objects.create(...)` (triggers model.save for code/link) + loop to create DEFAULT_STAGES.
  - On any Exception: collect `{"row": i, "error": str(e)}`, skipped +=1 .
- **Response**:
  - **201** (all good): `{"created": N, "skipped": 0, "errors": []}`
  - **207** (partial): same with errors list populated.
- **Audit**: `log_action(request.user, 'imported', 'Job', None, f"Imported {created} jobs from CSV (skipped: {skipped})")`.
- Matches `candidates/views_export.py` pattern exactly (ValidationError early, dedup, choice helper, atomic, counts, 207).

> [!TIP]
> Use Export first to generate a template CSV with exact headers/columns (incl. `client_name`). Import tolerant of partial failures (warnings for missing clients are non-blocking); errors are row-indexed (1-based, start=2). Matches `candidates/views_export.py` (ValidationError, dedup, _get_choice, atomic tx, 201/207 semantics).

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

