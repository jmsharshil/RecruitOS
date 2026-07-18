# Jobs Module Documentation

## Overview
Manages job requisitions/positions. Linked to clients, assigned to recruiters, with multi-stage pipeline.

**Key Models**: Job, Stage

**Statuses**: open, closed, on-hold

**Hiring For**: self or client

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
- **List**: `GET /api/v1/jobs/?status=open&client=uuid`
  - Role-based: Admin=all (org), Manager=created_by=user, Recruiter=assigned_recruiters=user. `is_deleted=False`, org filter.
  - **Response (200)**: List of JobSerializer (includes stages, candidate_count computed, client_name, assigned_recruiters).
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
        "resume_upload_link": "https://frontend/upload/job-uuid-here"
      }]
    }
    ```

- **Create**: `POST /api/v1/jobs/`
  **Request Body**:
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
  **Response (201)**: Full Job object + auto-created default Stages (from `DEFAULT_STAGES` in `perform_create`), generated `resume_upload_link`.

- **Retrieve**: `GET /api/v1/jobs/{id}/` — full details with nested stages, counts, etc.

- **Update**: `PATCH /api/v1/jobs/{id}/` — partial updates (e.g. change title, add skills, reassign recruiters).

- **Delete**: Soft-delete via `is_deleted=True`.

- **Change Status**: `PATCH /api/v1/jobs/{id}/status/`
  **Request Body**:
  ```json
  {
    "status": "closed"
  }
  ```
  **Response (200)**: `{"status": "closed", "message": "Job status updated"}` (or full job).

### Stages Management (JobViewSet actions)
- **Add Stage**: `POST /api/v1/jobs/{id}/stages/`
  **Body**:
  ```json
  {
    "name": "Final Interview",
    "order": 5,
    "color": "green"
  }
  ```
  **Response (201)**: Created Stage object.

- **Update Stage**: `PATCH /api/v1/jobs/{id}/stages/{stage_pk}/`
  **Body**: `{"color": "amber", "name": "Updated Name"}`
  **Response (200)**: Updated stage.

- **Delete Stage**: `DELETE /api/v1/jobs/{id}/stages/{stage_pk}/`
  - Only if no candidates in that stage.
  - **Response (204)**: No content.

- Uses `StageBriefSerializer` in job responses.

### Upload Link
- **GET /api/v1/jobs/{id}/upload-link/**
  - Returns:
    ```json
    {
      "resume_upload_link": "https://frontend.example.com/upload/{job-uuid}"
    }
    ```
  - The link points to global frontend URL that hits `PublicUploadView` backend with job_uuid.

### Export Jobs (CSV) - Matches JobExportView
- **Endpoint**: `GET /api/v1/jobs/export/?status=open`
- **Auth**: IsAuthenticated; role-scoped QS (`created_by` for Manager, `assigned_recruiters` for Recruiter, org + not deleted).
- **Query**: `?status=open` (filters Job.status).
- **Logic**: Builds rows with client.company_name, skills as comma str, safe float for budget.
- **CSV Headers** (`JOB_EXPORT_HEADERS`): `title, min_experience, max_experience, location, openings, priority, job_type, job_mode, hiring_for, client_name, status, skills, education, budget, description`
- **Response**: `jobs_export.csv` download via `generate_csv_response`.
- Logs `log_action(..., 'exported', 'Job', None, f"Exported {len} jobs")`.

### Import Jobs (CSV) - Matches JobImportView
- **Endpoint**: `POST /api/v1/jobs/import/`
- **Auth**: `IsAdminOrManager`, MultiPartParser.
- **Body**: multipart with `file` CSV.
- **Required**: `title, min_experience, max_experience, location`.
- **Logic** (per row, errors by row# starting at 2):
  - Client lookup by `client_name` (iexact, org, not deleted); warn in errors if not found but still create job.
  - Parse skills as comma-split, ints/floats with defaults, choice fields (status, priority, job_type, etc.) validated with fallback to defaults (e.g. OPEN, MEDIUM, PERMANENT, OFFICE, SELF).
  - Auto-create default Stages (same as JobViewSet.perform_create).
  - Dedup not explicit but org+title implicit via model.
- **Response**:
  - **201** (success): `{"created": 5, "skipped": 0, "errors": []}`
  - **207** (partial):
    ```json
    {
      "created": 3,
      "skipped": 2,
      "errors": [
        {"row": 2, "error": "Client 'Unknown' not found. Job will be created without a client."},
        {"row": 4, "error": "Invalid value for priority"}
      ]
    }
    ```
- Logs summary `log_action(..., 'imported', 'Job', None, ...)`.

> [!TIP]
> Export first to get template with exact columns (including client_name matching). Import supports partial failures with detailed row errors.

## Steps in Job Lifecycle
1. **Creation** (`POST /jobs/`): Includes all fields (skills list, client FK, assigned_recruiters M2M), auto-calls `perform_create` to create `DEFAULT_STAGES` (Screening to Hired) and set `resume_upload_link`.
2. **Stage Management**: Use dedicated actions for add/update/delete (with order/color; prevents delete if candidates linked via Application).
3. **Assignment & Visibility**: RBAC querysets filter by role (Manager=own created, Recruiter=assigned); notifies recruiters.
4. **Sourcing**: `GET /jobs/{id}/upload-link/` returns frontend global link → `PublicUploadView(/candidates/upload/{job_uuid}/, AllowAny)` which creates Candidate+Application (first stage).
5. **Pipeline**: Handled in candidates module via Application (current_stage FK to this Job's Stage, move-stage/schedule/send-to-client actions, status sync on Hired).
6. **Monitoring/Updates**: List includes `candidate_count`, nested stages/briefs; PATCH status or details; `log_action` audited.
7. **Bulk Data**: Export (role-scoped with ?status=, full headers, client_name), Import (multipart CSV, required fields, client lookup with warnings, choice validation+defaults, auto-stages, 201/207 with errors array).
8. **Closure**: Set status=closed; supports on-hold; soft-delete via BaseModel.

## Sample Responses

**Job List Item**:
```json
{
  "id": "job-uuid",
  "code": "JOB-000001",
  "title": "Senior Python Developer",
  "client_name": "Tech Corp",
  "status": "open",
  "priority": "high",
  "openings": 3,
  "assigned_recruiters": [...],
  "stages": [{"name": "Screening", "order": 1, "color": "slate"}, ...],
  "candidate_count": 12,
  "resume_upload_link": "https://.../upload/{uuid}"
}
```

**Stage Management Response**:
```json
{
  "id": "stage-uuid",
  "name": "Final Interview",
  "order": 5,
  "color": "emerald"
}
```

**Upload Link**:
```json
{
  "resume_upload_link": "https://frontend.app/upload/job-uuid-here"
}
```

**Export/Import Responses**: See Key APIs section above (matches `jobs/views.py` JobExportView/JobImportView exactly, including row errors, client_name iexact match, fallback choices, auto DEFAULT_STAGES creation, log_action).

## Integration Points
- **Clients Model**: FK + company_name used in import matching (Client.objects.filter(company_name__iexact=..., organization=...)); supports hiring_for=client for pipeline.
- **Accounts**: M2M assigned_recruiters for filtering/notifications; UserRole drives querysets in JobViewSet, CandidateViewSet, ApplicationViewSet.
- **Candidates Module**: **All linkage via Application** (unique_together on organization/candidate/job); current_stage points to Job's Stages. Public upload, parse_resume, export/import, calendar/events, move-stage etc. all reference Job. Pool candidates have no Application.
- **Notifications & Audit**: `log_action` on create/update/status/stages/export/import (with counts); notifications on assignment, uploads (to assigned_recruiters).
- **Shared**: `BaseModel` (soft-delete, org scoping everywhere), `StageBriefSerializer`, `JobBriefSerializer`, CSV utils (`JOB_EXPORT_HEADERS`, `JOB_IMPORT_REQUIRED`, parse/generate), `DEFAULT_STAGES`, choice enums (JobStatus, Priority, HiringFor, JobTypes, JobModes with safe defaults in import).
- **URLs/Views/Serializers**: Exact paths in `jobs/urls.py` (`export/`, `import/`, `{id}/upload-link/`, `{id}/stages/` etc.), serializers support writable fields, computed counts, nested briefs. Fully synced with candidates.md.

**Common Stages** (from `DEFAULT_STAGES`): Screening, HR Round, Technical, Client Round, Offer, Hired — auto-created on every Job create/import. Custom stages via API.

**Notes**:
- Fully updated with **body + response examples for ALL APIs** (CRUD, status, stages, upload-link, export/import with 201/207 semantics, query filters, role scoping, client matching, validation fallbacks).
- Matches provided `JobExportView` (QS + rows with float budget, skills join, log) and `JobImportView` (parse, client lookup with error note, choice parsing, auto-stages, 207 errors).
- Pipeline ownership moved to Application; upload link is frontend-global but backend job-scoped.
- Consistent RBAC, soft-delete, audit. Ready for reference/integration. Verified against code in `jobs/views.py`, `jobs/serializers.py`, `candidates/views.py`.

