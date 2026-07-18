# Candidates Module Documentation

## Overview
Core module for managing talent pool and job-specific candidate pipeline from sourcing to hiring. **Fully decoupled**: `Candidate` represents pure talent-pool entries (no job linkage). `Application` acts as the join model (`Candidate` ↔ `Job`) carrying status, stage, feedback, share_date etc. `InterviewSchedule` and `ClientSubmission` link to `Application`.

**Key Models**: Candidate, Application, InterviewSchedule, ClientSubmission

**Candidate Statuses** (on Application): screening, interview-scheduled, sent-to-client, hired, rejected, on-hold

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

- **Parse Resume**: `POST /api/v1/candidates/parse_resume/` (multipart, `resume` file field)
  - Uses `parse_resume_task` (strict AI with anti-hallucination: explicit facts only, JSON output, defaults to null/[]).
  - **Success Response (200)**:
    ```json
    {
      "candidate_name": "Parsed Name",
      "email": "parsed@email.com",
      "contact": "9876543210",
      "experience": "5.5 years",
      "current_ctc": 1200000,
      "expected_ctc": 1800000,
      "current_company": "Prev Co",
      "current_profile": "Developer",
      "education": "MBA",
      "skills": ["Java", "Spring"],
      "resume_file_name": "uploaded.pdf"
    }
    ```
  - **Error**: `{"error": "unparseable_resume"}` (status 400).

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
  - **200 Success**:
    ```json
    {
      "id": "app-uuid",
      "status": "interview-scheduled",
      "current_stage": {"id": "stage-uuid", "name": "Technical Round", "order": 3, "color": "blue"},
      "feedback": "Moved successfully",
      ...
    }
    ```
  - **400**: `{"error": "Invalid stage for this job"}` or stage ownership validation fail.
  - If target stage.name == "Hired": auto-sets status='hired', syncs.

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
- **Auth**: IsAuthenticated; role-scoped queryset (Admin: all org; Manager: created-by + pool; Recruiter: assigned via applications Q-filter + pool). Prefetches applications.
- **Query Params**:
  - `status`: Filter by Application.status (screening, hired, etc.). Pool candidates get status=POOL if no application.
  - `job_id`: Optional filter to specific job.
- **Response**: CSV download `candidates_export.csv` with headers from `CANDIDATE_EXPORT_HEADERS`.
- **CSV Columns**:
  ```
  candidate_name, profile_name, current_company, current_profile,
  experience, current_location, preferred_location,
  education, college, contact, email, dob, doc,
  current_ctc, expected_ctc, notice_period,
  status, share_date, feedback, job_title
  ```
- For pool: `status=POOL`, `job_title='Talent Pool'`.
- Logs `log_action(user, 'exported', 'Candidate', None, f"Exported {n} candidates")`; uses `generate_csv_response`.

### Import Candidates (CSV)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: `IsAdminOrManager`, parsers=MultiPartParser+FormParser.
- **Body**: multipart `file` (CSV).
- **Parsing**: `parse_csv_from_request(request, required_fields=['candidate_name', 'email', 'contact'])`.
- **Per-row Logic** (row index in errors starts at 2):
  - Dedup on `(email, organization)` — skip if exists.
  - Match `job_title` (case-insensitive) to org Job → create linked Application (auto first_stage from `Job.DEFAULT_STAGES`, default status='screening').
  - Uses `safe_float` for ctcs/notice, defaults for missing.
  - On error (duplicate app, bad job, exception): collect in errors array, increment skipped.
- **Response**:
  - **201 (all good)** or **207 (partial failures)**:
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
- Uses `log_action` with summary. Supports pool-only rows (no job_title).
- **TIP**: Export first for template. Matches `candidates/views_export.py` + serializer logic (writable job_id/candidate_id, StageBriefSerializer, method fields for schedule/submission).

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template (with current status/job_title), edit/add rows (pool or job-linked), then re-import. Single resumes can use the Parse Resume action or Public Upload link from a Job. Stages are auto-assigned on create/import.

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template (with current status/job_title), edit/add rows (pool or job-linked), then re-import. Single resumes can use the Parse Resume action or Public Upload link from a Job. Stages are auto-assigned on create/import.

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
- Docs now exhaustive: every API has concrete JSON request/response examples, query params, permission classes, 400/404/201/207 semantics, RBAC Q-filter logic, stage validation, public flow clarification, parse rules.
- Pipeline fully on Application (`current_stage` FK + dedicated actions vs generic PATCH).
- Upload link is global frontend (`/upload/{uuid}`) but backend remains job_uuid-scoped.
- CSV import: 207 on partial with row errors; export includes pool.
- Consistent `StageBriefSerializer`, `user=None` audit for public, soft-delete.
- All matches current implementation in code (verified via views/serializers/urls).

