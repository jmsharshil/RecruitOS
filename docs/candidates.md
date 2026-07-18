# Candidates Module Documentation

## Overview
Core module for managing talent pool and job-specific candidate pipeline from sourcing to hiring. **Fully decoupled**: `Candidate` represents pure talent-pool entries (no job linkage). `Application` acts as the join model (`Candidate` ↔ `Job`) carrying status, stage, feedback, share_date etc. `InterviewSchedule` and `ClientSubmission` link to `Application`.

**Key Models**: Candidate, Application, InterviewSchedule, ClientSubmission

**Candidate Statuses** (on Application): screening, interview-scheduled, sent-to-client, hired, rejected, on-hold

**Error Handling (All Endpoints)**
All errors are normalized by `common.exceptions.custom_exception_handler` (configured in `settings.py` REST_FRAMEWORK) into:
```json
{
  "error": "Authentication failed | Validation failed | Permission denied | specific-message",
  "detail": "Full error description (e.g. 'Authorization header must contain two space-delimited values')",
  "field_errors": {
    "field_name": ["list of messages"]
  }
}
```
- **401**: Missing/malformed `Authorization: Bearer <jwt-token>` (SimpleJWT).
- **400**: Validation or business rule errors (e.g. invalid stage, missing fields, unparseable resume); `field_errors` populated where applicable.
- **403/404/500**: Appropriate `error` type.
- Matches all examples below. See `common/exceptions.py` for details.

**Key Features**:
- Org-scoped talent pool (candidates with no Applications)
- Strict AI resume parsing (`parse_resume_task` wrapper around `parse_resume_ai` with anti-hallucination system prompt: explicit-only extraction, JSON-only, null/[] defaults, error path for unparseable resumes)
- Public resume upload (AllowAny) via global job upload link → AI parse → creates Candidate (+ linked Application if job provided)
- RBAC visibility: Recruiters see assigned-job Applications + pool; Managers see created-jobs + pool
- `log_action` supports `user=None` for public/system actions (with explicit organization)
- Threaded notifications via `simulate_resume_submission_notification` (tries Application first, falls back to Candidate for pool)
- All models inherit `BaseModel` (org scoping + soft-delete)
- CSV bulk import/export supports pool vs job-linked

## End-to-End Candidate Flow Diagram (with Talent Pool + Application)

```mermaid
flowchart TD
    A[Sourcing<br/>Add to Pool or Upload Resume to Job] --> B[Talent Pool (no Application)]
    B --> C[Link to Job → Create Application]
    C --> D[Screening (status on Application)]
    D --> E[Schedule Interview<br/>(linked to Application)]
    E --> F[Interview Completed + Feedback]
    F --> G[Decision: Move Stage?]
    G -->|Yes| H[Update current_stage on Application]
    G -->|Client Round| I[Client Submission (linked to Application)]
    H --> J[Collect Feedback]
    I --> K[Client Feedback Received]
    K --> L{Outcome?}
    L -->|Positive| M[Offer → Hired (update Application status)]
    L -->|Negative| N[Rejected/On-Hold]
    M & N --> O[log_action + Threaded Notification]
    O --> P[RBAC Visibility: Pool + Assigned Jobs]
    
    style A fill:#bae6fd
    style B fill:#a5f3fc
    style M fill:#86efac
    style N fill:#fda4af
```

## Key APIs

### CandidateViewSet (/api/v1/candidates/)
- **List**: `GET /api/v1/candidates/?search=rahul&status=screening`
  - Role-scoped queryset (pool + assigned via Q filter on applications).
  - **Response (200)**: Paginated list of `CandidateSerializer` (includes nested `applications` array).
    ```json
    {
      "count": 42,
      "results": [{
        "id": "cand-uuid",
        "candidate_name": "Rahul Sharma",
        "email": "rahul@example.com",
        "contact": "+919876543210",
        "experience": "6 years",
        "current_ctc": 1500000.0,
        "expected_ctc": 2200000.0,
        "current_company": "Tech Corp",
        "current_profile": "Senior Engineer",
        "resume_file_name": "rahul.pdf",
        "applications": []
      }]
    }
    ```

- **Create**: `POST /api/v1/candidates/`
  **Request Body**:
  ```json
  {
    "candidate_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "contact": "+919876543210",
    "experience": "6 years",
    "current_ctc": 1500000,
    "expected_ctc": 2200000,
    "current_company": "Tech Corp",
    "current_profile": "Senior Engineer",
    "resume_file_name": "resume.pdf",
    "education": "B.Tech Computer Science",
    "skills": ["Python", "Django"]
  }
  ```
  **Response (201)**: Full candidate object (id, timestamps, etc.) + empty applications array. Triggers `log_action` + notification.

- **Retrieve/Update**: `GET/PATCH /api/v1/candidates/{id}/` — full object, PATCH supports partial updates (e.g. update expected_ctc).

- **Parse Resume**: `POST /api/v1/candidates/parse-resume/` (multipart, `resume` file field; note hyphenated URL from `@action(url_path='parse-resume')`)
  - Uses `parse_resume_task` (strict AI with anti-hallucination: explicit facts only, JSON output, defaults to null/[]; falls back gracefully).
  - **Success Response (200)**: Serializer-compatible dict (see example above).
  - **Error Responses** (normalized by custom handler):
    ```json
    {
      "error": "unparseable_resume",
      "detail": "unparseable_resume",
      "field_errors": {}
    }
    ```
    (status 400 for AI failure; or 500 wrapped as {"error": "Parse failed: ..."} for other exceptions).

- **Upload Resume (per candidate)**: `POST /api/v1/candidates/{pk}/upload-resume/` (multipart `resume`)
  **Response (200)**: `{"message": "Resume uploaded and parsed successfully", "candidate": {...}}`

### ApplicationViewSet (/api/v1/applications/)
- **List**: `GET /api/v1/applications/?job_id=...&status=screening` — role-scoped (assigned jobs + pool).
  **Response**: List of ApplicationSerializer with nested CandidateBrief, JobBrief, StageBrief, interview_schedule, client_submission (method fields).

- **Create**: `POST /api/v1/applications/`
  **Request Body**:
  ```json
  {
    "job_id": "job-uuid-here",
    "candidate_id": "cand-uuid-here",
    "status": "screening",
    "feedback": "Good fit for role",
    "share_date": "2024-10-05",
    "current_stage_id": "stage-uuid-optional"
  }
  ```
  **Response (201)**: Full Application with auto-assigned first `current_stage` from `Job.DEFAULT_STAGES` if not provided. `log_action` + threaded notification.

- **Retrieve/Update**: `GET/PATCH /api/v1/applications/{id}/` — supports updating status, feedback, current_stage_id.

### Pipeline Actions (on ApplicationViewSet)
- **Move Stage**: `POST /api/v1/applications/{pk}/move-stage/`
  **Request Body**:
  ```json
  {
    "stage_id": "stage-uuid-here"
  }
  ```
  **Responses**:
  - **200 Success**: Updated `ApplicationSerializer` (see example in previous version).
  - **Error (normalized)**: 
    ```json
    {
      "error": "Invalid stage for this job",
      "detail": "Stage not found for this job",
      "field_errors": {}
    }
    ```
    (status 400). Validates that stage belongs to the Application's Job.
  - If target stage.name == "Hired": auto-sets `status='hired'` and syncs. All actions require valid `Authorization: Bearer <jwt>` header.

- **Schedule Interview**: `POST /api/v1/applications/{pk}/schedule-interview/`
  **Request Body**:
  ```json
  {
    "date": "2024-10-15",
    "time": "14:30:00",
    "mode": "online",
    "location": "https://zoom.us/j/123",
    "notes": "Focus on algorithms and system design",
    "interviewer": "interviewer-name"
  }
  ```
  **Response (201)**:
  ```json
  {
    "id": "sched-uuid",
    "application": "app-uuid",
    "date": "2024-10-15",
    "time": "14:30:00",
    "mode": "online",
    "location": "https://zoom.us/j/123",
    "notes": "...",
    "status": "interview-scheduled"
  }
  ```
  - Updates Application status to `interview-scheduled`, creates OneToOne InterviewSchedule, `log_action`.

- **Send to Client**: `POST /api/v1/applications/{pk}/send-to-client/`
  **Request Body** (optional):
  ```json
  {
    "notes": "Please review candidate for client round"
  }
  ```
  **Response (200)**: Updated ApplicationSerializer with `client_submission` populated (OneToOne), status=`sent-to-client`.
  - Restricted to jobs where `hiring_for == 'client'`.
  - Creates ClientSubmission, simulates notification/email, `log_action`.

### PublicUploadView (No Auth)
- **GET /api/v1/candidates/upload/{job_uuid}/**
  - `permission_classes = [AllowAny]`
  - **Response (200)**:
    ```json
    {
      "job_title": "Senior Developer",
      "company_name": "Tech Corp",
      "description": "Job desc here...",
      "requirements": "..."
    }
    ```

- **POST /api/v1/candidates/upload/{job_uuid}/** (multipart/form-data: `name`, `email`, `phone`, `resume` file)
  - Parses with `parse_resume_task` (fallback to form fields on error/duplicate).
  - Creates Candidate (uploaded_by=None), Application (first stage), `log_action(user=None, organization=job.org)`.
  - **Success Response (201)**:
    ```json
    {
      "message": "Resume uploaded successfully",
      "candidate_id": "cand-uuid",
      "application_id": "app-uuid",
      "parsed_data": { ... }
    }
    ```
  - Triggers notification to job's recruiters. Uses job_uuid for org isolation.

### CalendarEventsView
- **GET /api/v1/candidates/calendar/events/?start_date=2024-10-01&end_date=2024-10-31**
  - Role-scoped, aggregates from InterviewSchedule + ClientSubmission dates linked to Applications.
  - **Response (200)**:
    ```json
    [
      {
        "date": "2024-10-15",
        "events": [
          {"type": "interview", "time": "14:30", "candidate": "Rahul Sharma", "job": "Senior Dev", "notes": "..."},
          {"type": "client_submission", "candidate": "..."}
        ]
      }
    ]
    ```

### Export/Import (see below for full details; already matches code in candidates/views_export.py)

### Export Candidates (CSV)
- **Endpoint**: `GET /api/v1/candidates/export/?status=screening&job_id=uuid-here`
- **Auth**: `IsAuthenticated` (JWT `Authorization: Bearer <token>` required; see Error Handling section above). 
  - Role-scoped queryset (Admin: all org; Manager: `Q(applications__job__created_by=user) | Q(applications__isnull=True)`; Recruiter: assigned via applications Q-filter + pool). Prefetches applications. Uses `UserRole` from accounts.
- **Query Params**:
  - `status`: Filter by `Application.status` (screening, hired, etc.). Pool candidates default to `status=POOL`.
  - `job_id`: Optional filter to specific job (excludes pure pool if used).
- **Success Response**: CSV file `candidates_export.csv` (download) using `CANDIDATE_EXPORT_HEADERS` and `generate_csv_response`.
- **CSV Columns**:
  ```
  candidate_name, profile_name, current_company, current_profile,
  experience, current_location, preferred_location,
  education, college, contact, email, dob, doc,
  current_ctc, expected_ctc, notice_period,
  status, share_date, feedback, job_title
  ```
- For pool candidates: `status=POOL`, `job_title='Talent Pool'`.
- **Error Example** (malformed/missing token):
  ```json
  {
    "error": "Authentication failed",
    "detail": "Authorization header must contain two space-delimited values",
    "field_errors": {}
  }
  ```
  (status 401). Logs via `log_action(user, 'exported', 'Candidate', None, f"Exported {n} candidates (incl. pool)")`. Matches `CandidateExportView` in `candidates/views_export.py`.

### Import Candidates (CSV)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: `IsAdminOrManager` (JWT required), `parser_classes=[MultiPartParser, FormParser]`.
- **Body**: multipart/form-data with `file` (CSV).
- **Parsing**: `parse_csv_from_request(request, required_fields=CANDIDATE_IMPORT_REQUIRED)`.
- **Per-row Logic** (1-based row indexing for errors, starts at 2):
  - Dedup by `(email, organization)` — skip existing.
  - `job_title` (iexact match to org Job) creates linked `Application` (auto-assigns first stage from `Job.DEFAULT_STAGES`, defaults to `screening`).
  - `safe_float()` for CTCs/notice_period; sensible defaults for missing fields.
  - Errors (duplicate app, job not found, create exception) collected in array; row skipped.
- **Response** (201 full success or **207** partial):
  ```json
  {
    "created_candidates": 5,
    "created_applications": 3,
    "skipped": 2,
    "errors": [
      {"row": 3, "error": "Job 'Nonexistent' not found."},
      {"row": 5, "error": "Duplicate application for this candidate+job"}
    ]
  }
  ```
- Uses `log_action` with summary. Supports pure pool rows (no `job_title`). Matches `CandidateImportView` exactly (see `views_export.py`).

> [!TIP]
> **Export first** to get a compatible template (includes status/job_title columns). Edit and re-import. Use Parse Resume or Public Upload for single resumes. All errors use the normalized format documented above.

## Pipeline Steps (Detailed)
1. **Sourcing**: Use `CandidateViewSet` (pool), `ApplicationViewSet.create` (with `job_id`/`candidate_id`), `parse_resume` + upload-resume, or **PublicUploadView POST** (multipart to `/candidates/upload/{job_uuid}/`, `AllowAny`, `parse_resume_task` + form fallback, `log_action(user=None)`).
2. **Talent Pool**: Pure Candidates (no Application) visible via `Q(applications__isnull=True)` in role-scoped querysets.
3. **Linking/Application**: `POST /applications/` auto-assigns first stage from `Job.DEFAULT_STAGES`; uses writable `job_id`, `current_stage_id` in serializers.
4. **Progression**: PATCH Application or `POST /applications/{pk}/move-stage/` (validates stage ownership to Job, updates `current_stage` FK; "Hired" syncs status).
5. **Interview**: `POST /applications/{pk}/schedule-interview/` (creates OneToOne `InterviewSchedule`, sets status, method field in serializer).
6. **Client**: `POST /applications/{pk}/send-to-client/` (hiring_for check, creates `ClientSubmission`, status update).
7. **Calendar**: `GET /candidates/calendar/events/` aggregates from Application-linked schedules/submissions (role scoped).
8. **Bulk Ops**: Export (`?status=...&job_id=...`, pool support with special status/job_title), Import (dedup by (email, org), 201/207 with row-indexed error array, auto first-stage, `safe_float`).
9. **Notifications/Audit**: All paths (`perform_create`, actions, public, import/export) use `log_action` (user=None supported) + `simulate_resume_submission_notification` (Application-first fallback to Candidate for pool).

## Integration
- **Jobs**: Provides `stages`, `DEFAULT_STAGES`, `resume_upload_link` (from `GET /jobs/{id}/upload-link/`), `assigned_recruiters` (for Q-filter + notifications). Application links via FKs. Public upload job-scoped for isolation.
- **Accounts**: RBAC via `IsAdminOrManager`, role querysets (`Q(applications__job__assigned_recruiters=user) | Q(applications__isnull=True)` for recruiters), `BaseModel` soft-delete.
- **Clients**: `hiring_for=client` enables send-to-client flow.
- **Serializers/Views**: `CandidateSerializer`, `ApplicationSerializer` (with `StageBriefSerializer`, `JobBriefSerializer`, method fields for `interview_schedule`/`client_submission`), `candidates/views.py`, `candidates/serializers.py`, `candidates/views_export.py`, `candidates/urls.py`.
- **Utils**: Strict `parse_resume_ai` (anti-hallucination rules: JSON-only, explicit facts, error on failure), CSV with 207 partial, threaded notifications.

**Notes**: 
- **Error responses now fully documented** and improved via updated `custom_exception_handler` (handles 401 auth header issues like the reported "Authorization header must contain two space-delimited values", promotes view `{"error": "..."}` responses, populates `field_errors` for 400s). All examples updated to match.
- Docs exhaustive: concrete JSON for *all* endpoints/actions (including export/import 207s), query params, permissions (`IsAuthenticated`, `IsAdminOrManager`, `AllowAny`), RBAC Q-filters, validation (stage ownership, dedup, safe_float, choice fallbacks), parse anti-hallucination rules.
- Pipeline fully on `Application` (`current_stage` FK + dedicated `@action`s vs generic PATCH; auto first-stage from `Job.DEFAULT_STAGES` on create/import; "Hired" status sync).
- Upload link treated as global frontend URL; backend `PublicUploadView` remains job_uuid-scoped for org isolation (`log_action(user=None, organization=...)`).
- CSV: Export includes pool (`status=POOL`); Import uses 207 on partial failures with row-indexed errors; dedup by (email, org).
- Consistent use of `StageBriefSerializer`/`JobBriefSerializer`, method fields, `BaseModel` soft-delete, threaded notifications.
- All contracts verified against live code in `candidates/views*.py`, `serializers.py`, `urls.py`, `views_export.py`, `common/exceptions.py`, `utils.py`, `config/settings.py` (JWT + custom handler). Ready for frontend integration/testing.

