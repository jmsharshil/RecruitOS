# Candidates Module Documentation

## Overview
Core module for managing talent pool and job-specific candidate pipeline from sourcing to hiring. **Fully decoupled**: `Candidate` represents pure talent-pool entries (no job linkage). `Application` acts as the join model (`Candidate` ↔ `Job`) carrying status, stage, feedback, share_date etc. `InterviewSchedule` and `ClientSubmission` link to `Application`.

**Key Models**: Candidate (talent pool), Application (join to Job+Stage+status), InterviewSchedule (1:1 to Application), ClientSubmission (1:1 to Application)

**Choice Enums** (from models.py):
- `CandidateStatus` (on Application): "screening", "interview-scheduled", "sent-to-client", "hired", "rejected", "on-hold" (default: "screening")
- `InterviewMode`: "online", "in-person", "telephonic"
- `SubmissionStatus` (on ClientSubmission): "pending", "reviewed", "accepted", "rejected" (default: "pending")

All choice fields support case-insensitive lookup via `get_choice()` in imports. Status updates (e.g. to "hired") auto-sync in pipeline actions.

**Candidate & Application Fields Reference**

| Field | Type | Required? (Create) | Choices/Format | Default | Notes |
|-------|------|--------------------|----------------|---------|-------|
| **Candidate** | | | | | |
| `candidate_name` | string | **Yes** | - | - | Full name (key for dedup in import) |
| `email` | email | **Yes** | valid@email.com | - | Unique per org for dedup |
| `contact` | string | **Yes** | +91xxxxxxxxxx or phone | - | Phone number |
| `profile_name` | string | No | - | same as name | Short identifier |
| `current_profile` | string | No | - | "" | Current job title |
| `current_company` | string | No | - | "" | Current employer |
| `experience` | string | No | e.g. "5 years" | "0 years" | Experience summary |
| `current_location` / `preferred_location` | string | No | - | "" | Locations |
| `education` / `college` | string | No | - | "" | Qualifications |
| `dob` / `doc` | date | No | YYYY-MM-DD | null | Date of birth / date of joining? |
| `current_ctc` / `expected_ctc` / `offer_in_hand` | decimal | No | >=0 | 0 | Compensation figures (use safe_float in import) |
| `notice_period` | string | No | e.g. "30 days" | "Not specified" | Notice period |
| `reason_for_change` | text | No | - | "" | Why looking |
| `skills` | array | No | ["Python", ...] | [] | From AI parse or manual |
| `resume_file_name` | string | No | - | "" | For display |
| `resume` | file | No (upload separate) | PDF/DOC | null | FileField |
| **Application** | | | | | |
| `job_id` | UUID | Yes (for app) | Valid Job UUID | - | Links to job (write-only) |
| `candidate_id` | UUID | Yes (for app) | Valid Candidate UUID | - | Links to candidate (write-only) |
| `current_stage_id` | UUID | No | Valid Stage for job | first stage | Write-only |
| `status` | string | No | see CandidateStatus above | "screening" | Syncs with stages |
| `feedback` | text | No | - | "" | Interview/client notes |
| `share_date` | date | No | YYYY-MM-DD | today | When shared |
| **InterviewSchedule** | | | | | |
| `date` | date | **Yes** (schedule) | YYYY-MM-DD | - | - |
| `time` | time | **Yes** | HH:MM:SS | - | - |
| `mode` | string | **Yes** | "online", "in-person", "telephonic" | - | - |
| `interviewer_name` | string | No | - | "" | - |
| `notes` | text | No | - | "" | - |
| **ClientSubmission** | | | | | |
| `status` | string | No | "pending","reviewed","accepted","rejected" | "pending" | Client response |
| `client_feedback` | text | No | - | "" | - |
| `client_rating` | int | No | 1-5 | null | - |

**Notes**: Required for import = `candidate_name`, `email`, `contact` (plus `job_title` optional for linking). Use `assigned_recruiter_ids` pattern not applicable here; RBAC via Q on recruiter assignment to job. All decimals use `Decimal`/`safe_float`. AI parse populates many fields from resume. See `utils.py` for `parse_resume_ai`, `normalize_phone`.

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
- RBAC enforced via `common.permissions` (`IsAuthenticated` for list/create/update/parse/upload/export/import + pipeline actions, `IsAdminOrManager` for job mutations, `IsAdmin` for destroy) + role-scoped `get_queryset()` (using `Q` filters with `organization=user.organization`, pool visibility via `Q(applications__isnull=True)`, `Q(applications__job__created_by=user | assigned_recruiters=user)`). Recruiters can now add/import/export candidates (pool + their assigned jobs); Managers see created-jobs + pool.
- `log_action` supports `user=None` for public/system actions (with explicit organization)
- Threaded notifications via `simulate_resume_submission_notification` (tries Application first, falls back to Candidate for pool)
- All models inherit `BaseModel` (org scoping + soft-delete)
- CSV export (pool-aware with special status/job_title); CSV/Excel import (via updated `parse_csv_from_request` supporting `.csv`/`.xlsx`/`.xls`, header normalization, row-indexed errors, recruiter guards) supports pool vs job-linked.

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
- **Auth**: Uses `get_permissions()` — `IsAuthenticated()` for list/retrieve/create/update/parse-resume/upload-resume; `IsAdmin()` for destroy; `IsAdminOrManager()` otherwise. Role-scoped QS via `common.permissions` integration.
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
  **Step-by-Step**:
  1. Auth as any role (`IsAuthenticated` via get_permissions()).
  2. Prepare body using fields from reference table above (at minimum `candidate_name`, `email`, `contact`).
  3. POST to `/api/v1/candidates/`. Serializer creates Candidate (org-scoped, uploaded_by=current_user).
  4. `perform_create` logs action + triggers notification (pool entry).
  5. Returns full object with empty `applications: []` (can link later via Application create).
  6. For bulk, prefer Import endpoint.

  **Full Request Body Example** (all common fields; **required** marked):
  ```json
  {
    "candidate_name": "Rahul Sharma",           // **required**
    "email": "rahul@example.com",               // **required**
    "contact": "+919876543210",                 // **required**
    "profile_name": "RahulS",                   // optional
    "current_profile": "Senior Python Engineer", // optional
    "current_company": "Tech Corp",             // optional
    "experience": "6 years",                    // optional
    "current_location": "Bangalore",            // optional
    "preferred_location": "Remote",             // optional
    "education": "B.Tech Computer Science",     // optional
    "college": "IIT Delhi",                     // optional
    "dob": "1995-05-15",                        // optional
    "doc": "2020-01-01",                        // optional
    "current_ctc": 1500000.00,                  // optional (Decimal)
    "expected_ctc": 2200000.00,                 // optional (Decimal)
    "offer_in_hand": 1800000.00,                // optional
    "notice_period": "30 days",                 // optional
    "reason_for_change": "Better opportunity",  // optional
    "resume_file_name": "rahul_resume.pdf",     // optional
    "skills": ["Python", "Django", "AWS"]       // optional (array from parse)
  }
  ```
  **Full Success Response (201)**:
  ```json
  {
    "id": "cand-uuid-here",
    "candidate_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "contact": "+919876543210",
    "profile_name": "RahulS",
    "current_profile": "Senior Python Engineer",
    "current_company": "Tech Corp",
    "experience": "6 years",
    "current_location": "Bangalore",
    "preferred_location": "Remote",
    "education": "B.Tech Computer Science",
    "college": "IIT Delhi",
    "dob": "1995-05-15",
    "doc": "2020-01-01",
    "current_ctc": "1500000.00",
    "expected_ctc": "2200000.00",
    "offer_in_hand": "1800000.00",
    "notice_period": "30 days",
    "reason_for_change": "Better opportunity",
    "resume_file_name": "rahul_resume.pdf",
    "skills": ["Python", "Django", "AWS"],
    "applications": [],
    "uploaded_by": {"id": "user-uuid", "email": "recruiter@org.com", "full_name": "Recruiter"},
    "created_at": "2025-01-01T10:00:00Z",
    "organization": "org-uuid"
  }
  ```
  Errors normalized (e.g. duplicate email → 400 with field_errors or detail). Triggers `log_action` and notification.

- **Retrieve/Update**: `GET/PATCH /api/v1/candidates/{id}/` — full object, PATCH supports partial updates (e.g. update expected_ctc).

- **Parse Resume**: `POST /api/v1/candidates/parse-resume/` (multipart `resume` file; `@action(url_path='parse-resume')`)
  **Step-by-Step**:
  1. Authenticated user (any role) uploads resume PDF/DOC via multipart.
  2. `parse_resume_task` (Celery) calls `parse_resume_ai()` with hardened anti-hallucination system prompt ("Extract ONLY facts explicitly present in the resume. Never hallucinate. Output valid JSON only... Use null, [], 0 for missing.").
  3. AI (OpenAI/Azure) returns structured data; `normalize_phone()`, org-scoped duplicate check (by email).
  4. On success, returns data compatible with CandidateSerializer (no DB create).
  5. Use this data to then POST to /candidates/ or import.
  6. Fallback on AI failure: returns safe defaults.

  **Request**: Multipart form with `resume` file (no other body).

  **Full Success Response (200)** (populated from AI parse):
  ```json
  {
    "candidate_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "contact": "+91-9876543210",
    "experience": "6.5 years",
    "current_ctc": 1500000,
    "expected_ctc": 2500000,
    "current_company": "Current Corp",
    "current_profile": "Senior Backend Engineer",
    "education": "B.Tech from IIT",
    "skills": ["Python", "Django", "PostgreSQL", "AWS", "Docker"],
    "resume_file_name": "resume.pdf",
    "notice_period": "60 days",
    "reason_for_change": "Seeking new challenges"
  }
  ```

  **Error Responses** (normalized):
  - Unparseable (AI fail/hallucination guard):
    ```json
    {
      "error": "unparseable_resume",
      "detail": "Could not extract meaningful data from resume. Please try a clearer PDF or manual entry.",
      "field_errors": {}
    }
    ```
  - Other: `{"error": "Parse failed: ...", "detail": "...", "field_errors": {}}` (status 400/500 wrapped).
  See `candidates/utils.py:parse_resume_ai, parse_resume_task` for strict prompt and safe defaults. Matches anti-hallucination decision.

- **Upload Resume (per candidate)**: `POST /api/v1/candidates/{pk}/upload-resume/` (multipart `resume`)
  **Response (200)**: `{"message": "Resume uploaded and parsed successfully", "candidate": {...}}`

### ApplicationViewSet (/api/v1/applications/)
- **Auth**: Uses `get_permissions()` — `IsAuthenticated()` for list/retrieve/create/update + all pipeline actions (move-stage, schedule, send-to-client); `IsAdmin()` for destroy; `IsAdminOrManager()` otherwise. Role-scoped QS (assigned jobs only, as Applications require a Job).
- **List**: `GET /api/v1/applications/?job_id=...&status=screening` — role-scoped (assigned jobs).
  **Response**: List of ApplicationSerializer with nested CandidateBrief, JobBrief, StageBrief, interview_schedule, client_submission (method fields).

- **Create**: `POST /api/v1/applications/`
  **Step-by-Step**:
  1. Have valid Candidate and Job IDs (from prior creates or list).
  2. (Optional) Provide current_stage_id from that Job's stages.
  3. POST to create Application (unique_together on org+candidate+job enforced).
  4. If no current_stage_id, auto-assigns first stage from Job.DEFAULT_STAGES (order=1 "Screening").
  5. Sets default status="screening", logs action, triggers notification to recruiters.
  6. Returns full serializer with nested data.

  **Full Request Body** (using write-only IDs):
  ```json
  {
    "job_id": "job-uuid-here",           // **required**
    "candidate_id": "cand-uuid-here",    // **required**
    "status": "screening",               // optional; see CandidateStatus choices above
    "feedback": "Strong technical background, good cultural fit.",  // optional
    "share_date": "2025-01-10",          // optional (defaults to today)
    "current_stage_id": "stage-uuid-here" // optional; auto first-stage if omitted
  }
  ```
  **Full Success Response (201)**:
  ```json
  {
    "id": "app-uuid",
    "candidate": {
      "id": "cand-uuid",
      "candidate_name": "Rahul Sharma",
      "email": "rahul@example.com",
      "contact": "+919876543210",
      "current_profile": "Senior Engineer"
    },
    "job": {
      "id": "job-uuid",
      "title": "Senior Python Developer"
    },
    "current_stage": {
      "id": "stage-uuid",
      "name": "Screening",
      "color": "slate"
    },
    "status": "screening",
    "feedback": "Strong technical background, good cultural fit.",
    "share_date": "2025-01-10",
    "interview_schedule": null,
    "client_submission": null,
    "created_at": "2025-01-01T10:00:00Z"
  }
  ```
  Matches `perform_create` in views and import logic (first stage + status). `unique_together` prevents duplicate applications for same candidate-job.

- **Retrieve/Update**: `GET/PATCH /api/v1/applications/{id}/` — supports updating status, feedback, current_stage_id.

### Pipeline Actions (on ApplicationViewSet)
All actions use `IsAuthenticated` (via get_permissions), role-scoped QS (only applications for your jobs/pool), validate ownership. Use full `ApplicationSerializer` responses (with nested candidate/job/stage, method fields for schedule/submission). All update `log_action` + may trigger notifications. If moving to "Hired" stage, auto-sets `status="hired"`.

- **Move Stage**: `POST /api/v1/applications/{pk}/move-stage/`
  **Step-by-Step**:
  1. Get application ID and valid stage_id from job's stages (use Job retrieve first).
  2. POST with body.
  3. Validates stage belongs to the job (else 400).
  4. Updates `current_stage`, syncs status if "Hired", logs, returns updated serializer.
  5. Can be used for progression or rejections.

  **Full Request Body**:
  ```json
  {
    "stage_id": "stage-uuid-here"  // **required**; must match one of job.stages
  }
  ```
  **Full Success Response (200)**: Full ApplicationSerializer (see Create Application example below, with updated current_stage and status).

  **Error (400)**:
  ```json
  {
    "error": "Invalid stage for this job",
    "detail": "Stage not found for this job",
    "field_errors": {}
  }
  ```

- **Schedule Interview**: `POST /api/v1/applications/{pk}/schedule-interview/`
  **Step-by-Step**:
  1. Ensure application in valid stage.
  2. POST with interview details (uses InterviewMode choices).
  3. Creates OneToOne InterviewSchedule, sets Application status to "interview-scheduled", logs action + notification.
  4. Returns schedule data.

  **Full Request Body** (all fields):
  ```json
  {
    "date": "2025-02-15",                    // **required** (YYYY-MM-DD)
    "time": "14:30:00",                      // **required** (HH:MM:SS)
    "mode": "online",                        // **required**; choices: "online", "in-person", "telephonic"
    "location": "https://zoom.us/j/123456",  // optional (URL or address)
    "notes": "Focus on system design and Python expertise",  // optional
    "interviewer_name": "Alice Manager"      // optional
  }
  ```
  **Full Response (201)**:
  ```json
  {
    "id": "sched-uuid",
    "application": "app-uuid",
    "date": "2025-02-15",
    "time": "14:30:00",
    "mode": "online",
    "location": "https://zoom.us/j/123456",
    "notes": "Focus on system design and Python expertise",
    "interviewer_name": "Alice Manager",
    "status": "interview-scheduled",
    "created_at": "2025-01-01T12:00:00Z"
  }
  ```
  (Also updates the parent Application's status.)

- **Send to Client**: `POST /api/v1/applications/{pk}/send-to-client/`
  **Step-by-Step**:
  1. Verify job.hiring_for == "client" (else permission/business error).
  2. (Optional) Add notes.
  3. Creates ClientSubmission (OneToOne), sets status="sent-to-client", simulates notification, logs.
  4. Returns updated Application with client_submission populated.

  **Full Request Body**:
  ```json
  {
    "notes": "Strong technical profile with 6+ years in Django. Please review for client round."
  }
  ```
  **Full Response (200)**: Updated full `ApplicationSerializer` including:
  ```json
  {
    ...,
    "status": "sent-to-client",
    "client_submission": {
      "id": "sub-uuid",
      "status": "pending",
      "client_feedback": "",
      "client_rating": null,
      "sent_at": "2025-01-01T12:00:00Z",
      "sent_by": {"id": "...", "email": "..."}
    }
  }
  ```
  Restricted by job `hiring_for`. Uses `SubmissionStatus` choices internally.

### PublicUploadView (No Auth - for Job Upload Links)
- **GET /api/v1/candidates/upload/{job_uuid}/** (`permission_classes = [AllowAny]`)
  **Step-by-Step**: Frontend uses the `resume_upload_link` from Job to show job details publicly before upload.
  **Full Response (200)**:
  ```json
  {
    "job_title": "Senior Python Developer",
    "company_name": "Tech Corp",
    "description": "Build scalable backend services...",
    "requirements": "5+ years experience, strong Python/Django skills"
  }
  ```

- **POST /api/v1/candidates/upload/{job_uuid}/** (multipart/form-data: `name`, `email`, `phone`, `resume` file; AllowAny)
  **Step-by-Step**:
  1. Candidate fills form + uploads resume to public link (from JobViewSet /upload-link/).
  2. View extracts job by UUID for org scoping.
  3. Calls `parse_resume_task` on resume (with anti-hallucination prompt).
  4. On AI success or fallback to form fields (`name`→candidate_name, `email`, `phone`→contact normalized).
  5. Checks for duplicate by email+org; if exists, links to existing.
  6. Creates Candidate (uploaded_by=None, org from job), then Application (to this job, first DEFAULT_STAGES stage, status=screening).
  7. `log_action(user=None, verb='created', ... , organization=job.organization)`, simulate notification to assigned recruiters.
  8. Returns success with IDs.

  **Request**: Multipart with:
  - `name`: string (required for fallback)
  - `email`: string (required)
  - `phone`: string (required)
  - `resume`: file (PDF preferred for AI parse)

  **Full Success Response (201)**:
  ```json
  {
    "message": "Resume uploaded and parsed successfully",
    "candidate_id": "cand-uuid-here",
    "application_id": "app-uuid-here",
    "parsed_data": {
      "candidate_name": "Rahul Sharma",
      "email": "rahul@example.com",
      "contact": "+919876543210",
      "skills": ["Python", "Django"],
      "experience": "6 years",
      ...
    }
  }
  ```
  - On duplicate or parse fail, still creates with form data + logs. Job-scoped for isolation. See `candidates/views.py:PublicUploadView` and `utils.py:parse_resume_task`. Triggers threaded notification.

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

### Export/Import (CSV + Excel Support)
See `candidates/views_export.py` (RBAC updated, Excel via `common/utils_csv.py:parse_csv_from_request` using openpyxl). Export=CSV only; Import supports both. All fields align with **Candidate & Application Fields Reference** table above. Choices for `status` use `get_choice()` (case-insensitive).

### Export Candidates (CSV-only)
- **Endpoint**: `GET /api/v1/candidates/export/?status=screening&job_id=uuid`
- **Auth**: `IsAuthenticated()` (all roles including recruiters).
- **RBAC/Step-by-Step**:
  1. Uses same Q-filter as `CandidateViewSet.get_queryset()`: ADMIN=all, MANAGER=created jobs+pool, RECRUITER=assigned jobs + pool (`Q(applications__job__assigned_recruiters=user) | Q(applications__isnull=True)`).
  2. Optional query params: `?status=` (filters applications.status), `?job_id=` (specific job; excludes pure pool if used).
  3. Builds rows with special handling for pool candidates (`status=POOL`, `job_title="Talent Pool"`).
  4. Calls `generate_csv_response` with `CANDIDATE_EXPORT_HEADERS`.
  5. Logs `exported` action with count.

- **Full CSV Columns** (from `CANDIDATE_EXPORT_HEADERS`): `candidate_name,profile_name,current_company,current_profile,experience,current_location,preferred_location,education,college,contact,email,dob,doc,current_ctc,expected_ctc,notice_period,status,share_date,feedback,job_title`
- **Response**: File download `candidates_export.csv`. Pool-aware.

**Note**: Recruiters fully supported post-RBAC refactor.

### Import Candidates (CSV/Excel)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: `IsAuthenticated()` (recruiters restricted to pool or assigned jobs via M2M check).
- **Body**: multipart `file` (`.csv`/`.xlsx`/`.xls` supported).
- **Required** (per `CANDIDATE_IMPORT_REQUIRED`): `candidate_name`, `email`, `contact` (normalized headers).
- **Step-by-Step**:
  1. Export first to get template with exact columns (use Excel for ease).
  2. Fill data; `status` can use any case of choices (screening, hired, etc.); `job_title` for linking (optional for pure pool).
  3. Upload file.
  4. `parse_csv_from_request` handles Excel (openpyxl, data_only=True, skip empty, header regex normalize to snake_case) or CSV (utf-8-sig).
  5. Per row (index from 2): validate required, dedup by (email, org), optional job lookup by title__iexact + recruiter guard (for RECRUITER role).
  6. Create Candidate if new (uses safe_float for CTCs → Decimal, defaults), then Application if job (first stage from DEFAULT_STAGES, get_choice for status).
  7. Collect row-indexed errors (e.g. "Recruiter not assigned..."), count created/skipped.
  8. Atomic per row, final `log_action` with summary, return 201 or 207.

- **Full Response** (201 or 207):
  ```json
  {
    "created_candidates": 8,
    "created_applications": 5,
    "skipped": 2,
    "errors": [
      {"row": 4, "error": "Job 'Backend Engineer' not found."},
      {"row": 7, "error": "Recruiter not assigned to job 'Senior Dev'. Access denied."}
    ]
  }
  ```

> [!TIP]
> Use **Export** to generate template (includes all fields from table + status/job_title). Excel preferred for import (full support). Pure pool imports omit job_title. Dedup prevents duplicate candidates. Recruiter RBAC enforced per-row. Errors row-indexed (starts at 2). Matches updated `CandidateImportView`, `parse_csv_from_request()`, `safe_float()`, `get_choice()`. See table for all optional fields/choices. For single AI-powered uploads use PublicUploadView or Parse-Resume.

**Verification Note**: All sections now include full request/response bodies, required/optional markings, explicit choice values, step-by-step flows. Synced with code (views, models, serializers, utils, permissions, exception_handler). Docs are source of truth. Run `python manage.py check` to validate. Ready for API consumption.

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
- **Accounts**: RBAC via `common.permissions` classes (`IsAuthenticated`, `IsAdmin`, `IsAdminOrManager` etc. used in `get_permissions()` + `get_queryset()` with role-based Q-filters), `BaseModel` soft-delete.
- **Clients**: `hiring_for=client` enables send-to-client flow.
- **Serializers/Views**: `CandidateSerializer`, `ApplicationSerializer` (with `StageBriefSerializer`, `JobBriefSerializer`, method fields for `interview_schedule`/`client_submission`), `candidates/views.py`, `candidates/serializers.py`, `candidates/views_export.py`, `candidates/urls.py`.
- **Utils**: Strict `parse_resume_ai` (anti-hallucination rules: JSON-only, explicit facts, error on failure), CSV with 207 partial, threaded notifications.

**Notes**: 
- **RBAC fully centralized**: `get_permissions()` on `CandidateViewSet`/`ApplicationViewSet` (mirrors `JobViewSet`) uses `IsAuthenticated`, `IsAdmin`, `IsAdminOrManager` from `common.permissions`; `get_queryset()` applies role-specific Q-filters (pool visibility for candidates, assigned_recruiters for recruiters).
- **Error responses now fully documented** and improved via updated `custom_exception_handler` (handles 401 auth header issues like the reported "Authorization header must contain two space-delimited values", promotes view `{"error": "..."}` responses, populates `field_errors` for 400s). All examples updated to match.
- Docs exhaustive: concrete JSON for *all* endpoints/actions (including export/import 207s), query params, permissions (`IsAuthenticated`, `IsAdmin`, `IsAdminOrManager`, `AllowAny`), RBAC Q-filters, validation (stage ownership, dedup by (email+org), safe_float, _get_choice for status, Decimal for ctc), parse anti-hallucination rules, Excel support contract.
- Pipeline fully on `Application` (`current_stage` FK + dedicated `@action`s vs generic PATCH; auto first-stage from `Job.DEFAULT_STAGES` on create/import; "Hired" status sync).
- Upload link treated as global frontend URL; backend `PublicUploadView` remains job_uuid-scoped for org isolation (`log_action(user=None, organization=...)`).
- **CSV/Excel**: Export remains CSV-only (pool support with `status=POOL`); Import now supports Excel (`.xlsx`/`.xls` via openpyxl + CSV), uses 207 on partial failures with row-indexed errors (starts at 2), header normalization, dedup by (email, org). See `common/utils_csv.py`.
- Consistent use of `StageBriefSerializer`/`JobBriefSerializer`, method fields, `BaseModel` soft-delete, threaded notifications.
- All contracts verified 1:1 against live code in `candidates/views*.py` (now with `get_permissions`), `serializers.py`, `urls.py`, `views_export.py`, `common/utils_csv.py`, `common/permissions.py`, `common/exceptions.py`, `utils.py`, `config/settings.py` (JWT + custom handler + openpyxl in requirements). Ready for frontend integration/testing.

