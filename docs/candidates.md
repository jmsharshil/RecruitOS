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

### CandidateViewSet & ApplicationViewSet (DRF)
- **List/Create/Update**: `GET/POST/PATCH /api/v1/candidates/` and `/api/v1/applications/`
  - `get_queryset()` uses complex Q filters: `Q(applications__job__assigned_recruiters=user) | Q(applications__isnull=True)` (distinct) for Recruiter visibility of assigned + pool; similar for Manager (`created_by`).
  - `perform_create()` centralizes: creates Candidate/Application, calls `log_action`, triggers threaded notification via `simulate_resume_submission_notification`. For Applications, auto-assigns first default `current_stage` from Job.
  - Supports writable PKs for `job_id`, `current_stage_id`; nested serializers for brief info (CandidateBrief, JobBrief, StageBrief).
- **Parse Resume Action**: `POST /api/v1/candidates/parse_resume/` (file upload) — uses `parse_resume_task` (AzureOpenAI + PDF extractors with fallback, normalize_phone, safe coercion, org-scoped duplicate check by email). Returns serializer-compatible dict or `{"error": "unparseable_resume"}`.
- **Calendar Events**: `GET /api/v1/candidates/calendar/events/?start=...&end=...` — now filters via Application/InterviewSchedule (updated from old Candidate direct link).

### Stages & Pipeline Actions (ApplicationViewSet)
- **Move Stage**: `POST /api/v1/applications/{pk}/move-stage/` with `{"stage_id": "stage-uuid"}`
  - Validates stage belongs to the Application's Job.
  - Updates `current_stage`; if stage.name == "Hired", also sets status = 'hired'.
  - Returns updated ApplicationSerializer data; audited via `log_action`.
- **Schedule Interview**: `POST /api/v1/applications/{pk}/schedule-interview/` (with date, time, mode, etc.)
  - Creates linked `InterviewSchedule` (OneToOne to Application), sets status=`interview-scheduled`.
- **Send to Client**: `POST /api/v1/applications/{pk}/send-to-client/`
  - Only for jobs with `hiring_for=client`; creates `ClientSubmission`, sets status=`sent-to-client`, simulates email notification.
- Stages are Job-specific (defaults auto-created on Job creation: Screening, HR Round, Technical, Client Round, Offer, Hired). `StageBriefSerializer` used in responses for `current_stage`.

### Public Resume Upload (No Auth)
- **Upload Link**: Global (obtained via `GET /api/v1/jobs/{job_id}/upload-link/` which returns `{"resume_upload_link": "https://frontend.app/upload/{job-uuid}"}` — a public frontend URL not requiring job-specific auth in the link itself).
- **Backend Endpoint**: `GET/POST /api/v1/candidates/upload/{job_uuid}/` (`PublicUploadView`, permission=AllowAny)
  - GET: returns public job details (title, description, company).
  - POST (multipart/form-data: name, email, phone, resume): Uses `parse_resume_task` (which calls strict `parse_resume_ai` with anti-hallucination prompt), creates `Candidate(uploaded_by=None)` + linked `Application` (with first default stage); falls back to form fields on parse error/duplicate. Calls `log_action(None, ..., organization=job.organization)`.
- On success: triggers `simulate_resume_submission_notification` to job's assigned recruiters.
- Note: Always job-linked (uses job to determine organization); no pure global pool upload via public endpoint (use authenticated CandidateViewSet for pool).

### Export Candidates (CSV)
- **Endpoint**: `GET /api/v1/candidates/export/`
- **Auth**: IsAuthenticated (role-scoped queryset via `get_queryset` logic: Admin=all, Manager=created jobs + pool, Recruiter=assigned jobs + pool; always `is_deleted=False`, org-scoped). Uses prefetch on applications.
- **Query Params** (optional; filters exclude pure pool candidates): `?status=screening&job_id=<uuid>`
  - `status`: filters Application.status (e.g. screening, hired).
  - `job_id`: filters by specific job.
- **Logic**: For each candidate, uses first non-deleted Application (or defaults to status=POOL, job_title='Talent Pool'). Formats dates, CTCs, etc.
- **CSV Columns** (`CANDIDATE_EXPORT_HEADERS`):
  ```
  candidate_name, profile_name, current_company, current_profile,
  experience, current_location, preferred_location,
  education, college, contact, email, dob, doc,
  current_ctc, expected_ctc, notice_period,
  status, share_date, feedback, job_title
  ```
- Logs `log_action(..., 'exported', 'Candidate', ...)` and returns downloadable `candidates_export.csv` via `generate_csv_response`.

### Import Candidates (CSV)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: IsAdminOrManager only.
- **Body**: multipart/form-data with `file` (CSV).
- **Parses** using `parse_csv_from_request` (requires `candidate_name`, `email`, `contact`; `job_title` optional).
- **Logic** (per row, 1-based indexing for errors):
  - Dedup by email+organization (update not performed; skip create if exists).
  - If `job_title` provided + exact match to org Job (case-insensitive), create Application (with first_stage from Job, status default=screening).
  - Uses `safe_float` for CTCs, sensible defaults for missing fields, `uploaded_by=user`.
  - If Application would duplicate (unique_together), or job not found, or create fails → collect error, skip that row.
  - Supports cols: profile_name, current_profile, current_company, experience, current_location, preferred_location, education, college, dob, doc, current_ctc, expected_ctc, notice_period, status, feedback, share_date, reason_for_change, resume_file_name.
- **Response**: 201 (full success) or 207 (partial) with:
  ```json
  {
    "created_candidates": 5,
    "created_applications": 3,
    "skipped": 1,
    "errors": [{"row": 3, "error": "Job 'Missing Job' not found."}, ...]
  }
  ```
- **TIP**: Use **Export** first to get compatible template (includes status, job_title for linked rows). Handles pure pool (no job_title) or job-linked rows. Audited with summary log.

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template (with current status/job_title), edit/add rows (pool or job-linked), then re-import. Single resumes can use the Parse Resume action or Public Upload link from a Job. Stages are auto-assigned on create/import.

## Pipeline Steps (Detailed)
1. **Sourcing**: Recruiter adds via CandidateViewSet (to pool) or ApplicationViewSet (with job), or public upload via Job's global upload link (AI `parse_resume_task` → Candidate + Application with first stage).
2. **Talent Pool**: Pure Candidates (no Application) visible to all org recruiters via queryset filter.
3. **Linking**: Create Application (unique per org/candidate/job); auto-sets `current_stage` to first Job stage (Screening).
4. **Screening**: Update status/feedback on Application.
5. **Interview Scheduling**: `POST /applications/{pk}/schedule-interview/` → creates InterviewSchedule (OneToOne), updates status.
6. **Progression**: Use `POST /applications/{pk}/move-stage/` with stage_id (or PATCH with current_stage_id); updates stage/status/feedback; `log_action`.
7. **Client Round**: `POST /applications/{pk}/send-to-client/` (if job.hiring_for=='client') → creates ClientSubmission, sets sent-to-client status, simulates email.
8. **Feedback Loop**: Update feedback/rating on InterviewSchedule or ClientSubmission; move stage to Offer/Hired/Rejected.
9. **Notifications & Audit**: All actions (`perform_create`/`perform_update`, stage-move, etc.) trigger `log_action` and `simulate_*_notification` (Application-first fallback to Candidate for pool; supports user=None for public).
10. **Export/Import**: Full support for pool vs. job-linked via CSV (status, job_title, etc.); audited.

## Sample Responses

**Candidate (Pool or Base)**:
```json
{
  "id": "uuid",
  "candidate_name": "Rahul Sharma",
  "email": "rahul@example.com",
  "experience": "6 years",
  "current_ctc": "1500000.00",
  "resume_file_name": "rahul_resume.pdf",
  "applications": [{"job": "...", "status": "screening", ...}]
}
```

**Application (Job-linked with status/stage)**:
```json
{
  "id": "uuid",
  "candidate": {"candidate_name": "Rahul Sharma", ...},
  "job": "job-uuid",
  "status": "interview-scheduled",
  "current_stage": {"name": "Technical", "order": 3},
  "feedback": "Good problem solving skills",
  "share_date": "2024-10-01",
  "interview_schedule": {
    "date": "2024-10-15",
    "time": "14:30:00",
    "mode": "online"
  }
}
```

## Integration
- **Jobs**: Linked via `Application` (unique_together on org/candidate/job). Job has related applications + stages (current_stage FK). Public upload link from Job ties into Candidate creation.
- **Accounts**: `uploaded_by`, `assigned_recruiters`, `sent_by`, `created_by`; role-based querysets (Admin/Manager/Recruiter).
- **Notifications**: `simulate_resume_submission_notification(obj_id)` (prefers Application.id then falls back to Candidate for pool); threaded. Also simulates client email on send-to-client.
- **Audit**: `log_action` on all CRUD, stage moves, interview schedule, client submission, public upload (supports user=None with explicit org), export/import.
- **Common**: All models inherit `BaseModel` (org + soft-delete). Uses strict `parse_resume_task`/`parse_resume_ai`, CSV utils for pool+job-linked, `StageBriefSerializer`.
- **Clients**: Via Job.hiring_for/client → Application → ClientSubmission (with feedback/rating).

**Notes**: 
- Pool candidates (no applications) visible to all org recruiters via Q filter.
- `CalendarEventsView` uses Application + InterviewSchedule with role scoping.
- AI parsing hardened against hallucination (explicit-only, error JSON on failure).
- Stages progression via dedicated actions + auto-first-stage on create.
- Soft-delete everywhere (no hard deletes except possibly users).

