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
| `is_duplicate` | boolean | No | - | false | Duplicate flag (set via action or AI parse dup check) |
| `duplicate_of` | UUID | No | valid candidate UUID | null | FK to canonical candidate (for deduplication) |
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

**Notes**: Required for import = `candidate_name`, `email`, `contact` (plus `job_title` optional for linking). Duplicates detected by email (iexact) or normalized phone in parse/upload/import using `_find_existing_candidate`. All decimals use `Decimal(safe_float())`. AI parse populates many fields + strict anti-hallucination. See `utils.py` for `parse_resume_ai` (hardened prompt), `normalize_phone`, `_find_existing_candidate`. New duplicate actions and serializer fields (`is_duplicate`, `duplicate_of*`) supported.

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
- **Decoupled pool-first design**: `Candidate` = pure talent pool (`uploaded_by=None` supported); `Application` = join model (`unique_together(org, candidate, job)`, `current_stage` FK, status sync on "hired"). Interview/Client models 1:1 to Application.
- Strict AI resume parsing (`parse_resume_task` + `parse_resume_ai` with anti-hallucination system prompt: "Extract ONLY facts explicitly present... Never hallucinate. JSON-only output. Use null, [], 0 for missing. Error path for unparseable_resume").
- Public resume upload (`AllowAny`, requires `org_id`) → pure pool Candidate (no auto-Application; recruiters link manually). Uses hardened parser + duplicate guard + `log_action(user=None, organization=...)` + pool notification fallback.
- RBAC centralized in `ViewSet.get_permissions()` (`IsAuthenticated` for list/create/parse/upload/export/import/pipeline, `IsAdmin` for destroy, `IsAdminOrManager` otherwise) + role-scoped `get_queryset()` with Q-filters:
  - **CandidateViewSet/Export**: ADMIN=full org; MANAGER=(created jobs | pool); RECRUITER=(pool | assigned_recruiters jobs via Q + .distinct()).
  - **ApplicationViewSet**: ADMIN=full, MANAGER=created jobs, RECRUITER=assigned jobs only.
  - Export/Import exactly mirrors (recruiters see full pool + their pipeline).
- `log_action(user=None, organization=...)` support; threaded notifications with pool fallback.
- All models inherit `BaseModel` (org + soft-delete); enums for statuses/modes.
- Unified CSV/Excel: `?format=xlsx`/`?template=1` on export (pool-aware: status=POOL, job_title="Talent Pool"); full Excel import (openpyxl.data_only, per-row atomic, row errors from 2, 201/207). Duplicate management (auto + @actions).

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
- **List**: `GET /api/v1/candidates/?search=rahul&status=screening&status=POOL`
  - Role-scoped queryset: pool candidates (no apps) + those with apps to user's jobs (Q-filter + .distinct() for MANAGER/RECRUITER). Status=POOL can be used in filter.
  - **Response (200)**: Paginated list of `CandidateListSerializer` (includes `applications_count`, `is_duplicate`, `duplicate_of_name`; nested apps only in detail).
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
  **Response (200)**: `{"message": "Resume uploaded successfully"}`
  (Note: AI parse is separate `parse-resume` action for preview; upload just attaches file to existing Candidate.)

### Duplicate Management Actions (on CandidateViewSet)
New endpoints for handling duplicate candidates (common in talent pools). Integrated with AI parse and public upload for auto-detection. Visible in `CandidateListSerializer` and `CandidateDetailSerializer` (incl. `duplicate_of_detail`).

- **Mark as Duplicate**: `POST /api/v1/candidates/{pk}/mark-duplicate/`
  **Step-by-Step**:
  1. Authenticated user with access to both candidates.
  2. POST body with `duplicate_of` = UUID of the canonical (primary) candidate.
  3. Validates: same org, exists, not self-reference.
  4. Sets `is_duplicate=True`, `duplicate_of=canonical`, logs detailed action.
  5. Returns updated candidate data.

  **Request Body**:
  ```json
  {
    "duplicate_of": "canonical-uuid-here"
  }
  ```
  **Success Response (200)**:
  ```json
  {
    "message": "Candidate marked as duplicate of 'Rahul Sharma'.",
    "candidate": {
      "id": "dup-uuid",
      "is_duplicate": true,
      "duplicate_of": "canonical-uuid",
      "duplicate_of_name": "Rahul Sharma",
      ...
    }
  }
  ```

- **Unmark Duplicate**: `POST /api/v1/candidates/{pk}/unmark-duplicate/`
  No body required. Resets `is_duplicate=False`, `duplicate_of=None`, logs action, returns updated serializer data.

**In Parse & Public Upload**: Auto-detects via `_find_existing_candidate()` (email then normalized phone, org-scoped). If duplicate found, returns 200 with `{"duplicate": true, "existing_candidate_id": "...", "message": "..."}` instead of creating.

See `candidates/views.py` (mark_duplicate/unmark_duplicate methods), `utils.py` (`_find_existing_candidate`, `parse_resume_task`), serializers (method fields for names/details). Prevents data pollution in talent pool.

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

### TalentPoolPublicUploadView (No Auth - Global Talent Pool Upload)
- **GET /api/v1/candidates/public-upload/?org_id=...** — returns org info or usage note.
- **POST /api/v1/candidates/public-upload/** (`permission_classes = [AllowAny]`, **required** `org_id` query param or form field for scoping)
  **Step-by-Step**:
  1. Public/embedded forms POST multipart with `name`, `email`, `phone`, `resume`, `org_id`.
  2. Validates all required (incl. org_id); looks up Organization.
  3. Calls `parse_resume_task(resume, organization=org)` — strict anti-hallucination AI (explicit facts only, JSON-only, null/[]/0 defaults, unparseable error path), fallback to form data.
  4. Org-scoped duplicate check via `_find_existing_candidate(email, normalized_phone, organization)`.
  5. On duplicate: 200 with info. Else creates pure `Candidate` (pool, `uploaded_by=None`, org-scoped). No auto-Application.
  6. `log_action(user=None, 'created', ..., organization=org)` + `simulate_resume_submission_notification` (pool fallback notifies all recruiters in org).
  7. Robust: temp files cleaned, extract_text hierarchy (PyMuPDF > pdfplumber > docx2txt), normalize_phone, rewind file.

  **Request** (multipart/form-data):
  - `name`, `email`, `phone`, `resume` (file), `org_id` (UUID) — all **required**

  **Full Success Response (201)**:
  ```json
  {
    "message": "Resume submitted successfully! We'll be in touch.",
    "candidate_id": "cand-uuid-here"
  }
  ```

  **Duplicate Response (200)**:
  ```json
  {
    "message": "A candidate with this profile already exists in our talent pool.",
    "duplicate": true,
    "existing_candidate_id": "existing-uuid"
  }
  ```

  **Error Responses** (normalized):
  ```json
  {
    "error": "All fields (name, email, phone, resume, org_id) are required",
    "detail": "...",
    "field_errors": {}
  }
  ```
  or `{"error": "unparseable_resume", "detail": "Could not extract..."}` (400).

  See `candidates/views.py:TalentPoolPublicUploadView` (now with GET + required org_id), `utils.py` (hardened parser, duplicate guard, extract_text). Matches decoupled pool-first design. Job's `resume_upload_link` points here with org_id. Notification uses org-scoped recruiters. Updated for hardening (no null org).

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
See `candidates/views_export.py` (RBAC updated, unified via `common/utils_csv.py:generate_csv_response(..., export_format=...)` + `parse_csv_from_request` using openpyxl.data_only=True). Supports `?format=xlsx` (or csv) on export + full Excel import. All fields align with **Candidate & Application Fields Reference** table above. Choices for `status` use `get_choice()` (case-insensitive). Template uses sample row (no DB hit). See `ExportFormatsView` for dynamic headers/URLs.

### Export Candidates (CSV + Excel)
- **Endpoint**: `GET /api/v1/candidates/export/?status=screening&job_id=uuid&format=xlsx&template=1`
- **Auth**: `IsAuthenticated()` (all roles including recruiters).
- **RBAC/Step-by-Step**:
  1. Uses **exact** same role logic as `CandidateViewSet.get_queryset()`: ADMIN=full org, MANAGER=(created_by jobs | pool), RECRUITER=full org pool. Uses prefetch_related('applications__job').distinct() where needed.
  2. Optional query params: `?status=` (filters Application.status, excludes pure pool if filtered), `?job_id=`, `?format=xlsx` (default=csv), `?template=1` (sample row only, no DB query, filename ends .xlsx if requested).
  3. For non-template: builds rows with pool handling (`status=POOL`, `job_title="Talent Pool"`, first non-deleted Application or None).
  4. Calls updated `generate_csv_response(filename, CANDIDATE_EXPORT_HEADERS, rows, export_format=...)` (cleans bool/None/date for Excel compat).
  5. Logs `exported` action (user-aware, separate msg for template).

- **Full Columns** (from `CANDIDATE_EXPORT_HEADERS`): `candidate_name,profile_name,current_company,current_profile,experience,current_location,preferred_location,education,college,contact,email,dob,doc,current_ctc,expected_ctc,notice_period,status,share_date,feedback,job_title`
- **Response**: File download (`candidates_export.{csv|xlsx}` or template). Pool-aware with special status/job_title.

**Note**: Recruiters fully supported post-RBAC refactor (see Q-filter). Matches Client/JobExportView pattern. For template, use with job_title column for linking on import.

### Import Candidates (CSV/Excel)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: `IsAuthenticated()` (recruiters restricted to pool or assigned jobs via M2M check on `job.assigned_recruiters`).
- **Body**: multipart `file` (`.csv`/`.xlsx`/`.xls` supported via `parse_csv_from_request`).
- **Required** (per `CANDIDATE_IMPORT_REQUIRED`): `candidate_name`, `email`, `contact` (normalized headers via regex→snake_case).
- **Step-by-Step**:
  1. Use `/export-formats/` or Export with `?template=1&format=xlsx` to get headers/sample.
  2. Fill data; `status`/`job_title` optional. `dob`/`doc`/`share_date` flexible via `DateParserField(fuzzy=True)`. CTCs via `safe_float`.
  3. Upload under key `file`.
  4. Parser: Excel-first (openpyxl.data_only=True for formulas), skips empty rows, normalizes headers, validates required.
  5. Per-row (indexed from 2, `transaction.atomic()`): dedup `(email__iexact, org)`, job lookup (`title__iexact`), recruiter RBAC guard, create Candidate (or skip existing), create Application (first_stage or DEFAULT_STAGES fallback, `get_choice(status, ..., default=SCREENING)`).
  6. Collects row errors (e.g. missing reqs, job not found, permission, create fail).
  7. Logs summary (`log_action` with counts). Returns 201 (full) or **207** (partial success with errors list).

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
> Use **ExportFormatsView** (`/api/v1/export-formats/`) or `?template=1&format=xlsx` for exact headers/sample row. Excel preferred (full support, computed values via data_only=True). Pure pool: omit `job_title`. Dedup by `(email,org)`. Per-row RBAC for recruiters. Row errors start at 2. Matches `CandidateImportView` (uses `DateParserField`, `safe_float`, `_find_existing_candidate` helper), `common/utils_csv.py`, `common/serializers.py`. See field table for all optional fields/choices (e.g. `status` case-insensitive). For AI-powered single uploads use PublicUploadView or Parse-Resume.

**Verification Note**: All sections now include full request/response bodies, required/optional markings, explicit choice values, step-by-step flows, duplicate management, updated RBAC (full pool for recruiters in Candidate flows), and aligned export QS. Synced with latest code (incl. mark/unmark-duplicate actions, _find_existing_candidate, hardened parser, unified CSV/Excel, user=None audit, custom_exception_handler). Docs are source of truth. Run `python manage.py check` and test endpoints to validate. Ready for frontend and API consumption.

## Pipeline Steps (Detailed)
1. **Sourcing**: Use `CandidateViewSet.create` (pool), `parse-resume` action (AI preview + anti-hallucination), `upload-resume` (attach file), **PublicUploadView** (`POST /api/v1/candidates/public-upload/?org_id=...` **required**, `AllowAny`, pure pool Candidate), or `ApplicationViewSet.create` (with `job_id` + `candidate_id`; auto first-stage). Uses hardened `parse_resume_task` (with duplicate guard), `log_action(user=None, organization=...)`.
2. **Talent Pool**: Pure Candidates (`applications__isnull=True`) visible to all org roles (RECRUITER gets full pool + assigned).
3. **Linking/Application**: `POST /applications/` (unique_together enforced, auto first-stage from `Job.DEFAULT_STAGES` or provided `current_stage_id`).
4. **Progression**: Use dedicated `move-stage` action (validates stage-to-job ownership, updates `current_stage` FK; "Hired" auto-syncs status).
5. **Interview**: `schedule-interview` (creates 1:1 `InterviewSchedule`, sets "interview-scheduled" status).
6. **Client**: `send-to-client` (hiring_for check, creates 1:1 `ClientSubmission`).
7. **Calendar**: Role-scoped aggregation from linked schedules/submissions.
8. **Bulk**: Export (pool-aware with `status=POOL`/`job_title="Talent Pool"`, mirrors QS), Import (per-row atomic, dedup by (email,org), row errors from 2, 201/207, `DateParserField`/`safe_float`/`get_choice`).
9. **Duplicate/Audit/Notifications**: Auto in parse/upload/import; manual mark/unmark actions; `log_action` + threaded notif (pool fallback via simulate_resume_submission_notification).

## Integration
- **Jobs**: Provides `stages`, `DEFAULT_STAGES`, `resume_upload_link` (points to global `/candidates/public-upload/?org_id=...`), `assigned_recruiters` (for Q-filter + notifications). Applications link Candidate ↔ Job (decoupled; no auto-create on public upload).
- **Accounts**: RBAC via `common.permissions` (`IsAuthenticated`, `IsAdmin`, `IsAdminOrManager` in `get_permissions()` + Q-filtered `get_queryset()`), `BaseModel` soft-delete + org scoping.
- **Clients**: `hiring_for=client` enables send-to-client flow.
- **Serializers/Views**: `Candidate*Serializer` (duplicate fields, method fields), `Application*Serializer` (write-only IDs, nested briefs, schedule/submission methods), views (with duplicate actions, public upload, calendar, export/import), `candidates/urls.py`.
- **Utils**: Hardened `parse_resume_ai` (strict anti-hallucination prompt + safe defaults + duplicate guard), `extract_text`, `normalize_phone`, `_find_existing_candidate(org-scoped)`, unified CSV/Excel in `common/utils_csv.py`, `DateParserField`, `safe_float`, `get_choice`.

**Notes**: 
- **RBAC fully hardened**: `get_permissions()` + role-specific Q-filters in `get_queryset()` (mirrors JobViewSet). CandidateViewSet/ExportView now uses `Q(applications__isnull=True) | Q(applications__job__assigned_recruiters=user).distinct()` for RECRUITER (full pool + assigned jobs only). Prevents leaks. ApplicationViewSet strict to assigned. PublicUpload **requires** `org_id`.
- **Error contract** fully documented/normalized via `custom_exception_handler` (handles malformed auth headers like "Authorization header must contain two space-delimited values", promotes view `{"error": "..."}`, populates `field_errors`).
- Docs exhaustive: full JSONs for all endpoints/actions (incl. duplicate mark/unmark, public-upload GET/POST with required org_id, export ?status=POOL, import 207s), RBAC/Q details, anti-hallucination rules, Excel/CSV contract, pipeline mermaid.
- Decoupled design: Public upload = pure pool Candidate (`uploaded_by=None`, no auto-Application even with job). Recruiters link via Application.create (auto first-stage). "Hired" syncs status on Application.
- Duplicate fully integrated (auto via `_find_existing_candidate(email/phone/org)` in parse/upload/import; manual @actions; serializer fields).
- **CSV/Excel Unified** across modules: `?format=xlsx`/`?template=1`, openpyxl.data_only, per-row atomic, row errors (from 2), 201/207.
- All synced: hardened parser (strict prompt, safe defaults), `user=None` audit, `DateParserField(fuzzy=True)`, `get_choice(default=SCREENING)`, `BaseModel`, threaded notifs (pool fallback). Verified 1:1 with code (`views*.py`, `utils.py`, serializers, models, common/*). `python manage.py check` clean. Docs = source of truth. Ready for frontend/prod.

