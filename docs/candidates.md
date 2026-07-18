# Candidates Module Documentation

## Overview
Core module for managing talent pool and job-specific candidate pipeline from sourcing to hiring. **Fully decoupled**: `Candidate` represents pure talent-pool entries (no job linkage). `Application` acts as the join model (`Candidate` ↔ `Job`) carrying status, stage, feedback, share_date etc. `InterviewSchedule` and `ClientSubmission` link to `Application`.

**Key Models**: Candidate, Application, InterviewSchedule, ClientSubmission

**Candidate Statuses** (on Application): screening, interview-scheduled, sent-to-client, hired, rejected, on-hold

**Key Features**:
- Org-scoped talent pool (candidates with no Applications)
- Strict AI resume parsing (`parse_resume_ai` with anti-hallucination system prompt: explicit-only extraction, JSON-only, null/[] defaults, error path)
- Public resume upload (AllowAny) that does AI parse → creates Candidate + linked Application
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
  - `perform_create()` centralizes: creates Candidate/Application, calls `log_action`, triggers threaded notification via `simulate_resume_submission_notification`.
  - Supports writable PKs for `job_id`, `current_stage_id`; nested serializers for brief info.
- **Parse Resume Action**: `POST /api/v1/candidates/parse_resume/` (file upload) — uses `parse_resume_task` (AzureOpenAI + PDF extractors with fallback, normalize_phone, safe coercion, org-scoped duplicate check by email). Returns serializer-compatible dict or `{"error": "unparseable_resume"}`.
- **Calendar Events**: `GET /api/v1/candidates/calendar/events/?start=...&end=...` — now filters via Application/InterviewSchedule (updated from old Candidate direct link).

### Public Resume Upload (No Auth)
- **Endpoints**: `GET/POST /api/v1/candidates/upload/{job_uuid}/`
- `PublicUploadView` (permission=AllowAny): 
  - GET: returns public job details.
  - POST (multipart: name, email, phone, resume): AI parse via `parse_resume_ai` (strict prompt), creates `Candidate(uploaded_by=None)` + linked `Application` to the job; falls back to form fields on parse fail/duplicate. Calls `log_action(None, ..., organization=job.organization)`.
- On success: triggers notification to job's assigned_recruiters (or all recruiters for pool).

### Export Candidates (CSV)
- **Endpoint**: `GET /api/v1/candidates/export/`
- **Auth**: IsAuthenticated (role-based queryset).
- **Query Params** (optional, exclude pool if used): `?status=screening&job_id=<uuid>`
- **Logic**: Prefetch applications, use first non-deleted app or status='POOL', job_title='Talent Pool' for pure pool.
- **CSV Columns** (`CANDIDATE_EXPORT_HEADERS`):
  ```
  candidate_name, profile_name, current_company, current_profile,
  experience, current_location, preferred_location,
  education, college, contact, email, dob, doc,
  current_ctc, expected_ctc, notice_period,
  status, share_date, feedback, job_title
  ```
- Logs action with `log_action`.

### Import Candidates (CSV)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: IsAdminOrManager
- **Parses** using `parse_csv_from_request` (requires `candidate_name`, `email`, `contact`; `job_title` optional).
- **Logic** (per row):
  - If `job_title` provided and matches org Job → create/link Application.
  - Dedup Candidate by (email, organization); create if new (with safe_float for CTC, defaults, `uploaded_by=user`).
  - If Application exists for (candidate, job, org) → skip with error.
  - Supports additional cols: profile_name, current_profile, experience, locations, education, ctc, notice_period, status, feedback, share_date, reason_for_change, resume_file_name.
- **Response**: 201 full success or 207 partial with row errors; counts for created_candidates, created_applications, skipped.
- **TIP**: Export first to get template (compatible format), edit, re-import. Handles pool (no job_title) or job-linked.

> [!TIP]
> Use **Export** to download template. Import supports both talent-pool and job-specific rows via optional `job_title`. AI-powered resume parse available for single uploads.

## Pipeline Steps (Detailed)
1. **Sourcing**: Recruiter adds via CandidateViewSet (to pool or with job→Application), or public upload (AI parse_resume_task).
2. **Talent Pool**: Pure Candidates (no Application) visible to all org recruiters.
3. **Linking**: Create Application to attach to Job (unique per org/candidate/job).
4. **Screening**: Set status/feedback on Application.
5. **Interview Scheduling**: Create InterviewSchedule linked to Application; triggers threaded reminder notification.
6. **Progression**: Update Application.current_stage, status, feedback; log_action.
7. **Client Submission**: Create ClientSubmission linked to Application (status=sent-to-client); simulate email.
8. **Feedback Loop**: Update client_feedback/rating on submission; move to hired/rejected.
9. **Notifications & Audit**: All via `perform_create`/`update`, `simulate_*_notification` (Application-first with DoesNotExist fallback to Candidate for pool), `log_action` (supports public user=None).
10. **Export/Import**: Full support for pool + linked via CSV utils.

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
- **Jobs**: Linked via `Application` (M2M effectively, with unique_together on org/candidate/job). Job has related applications.
- **Accounts**: `uploaded_by`, `assigned_recruiters`, `sent_by`; notifications to UserRole.RECRUITER.
- **Notifications**: Uses `simulate_resume_submission_notification(obj_id)` that prefers Application then falls back to Candidate; supports pool vs job-linked messages.
- **Audit**: `log_action` on create/update/export/import/public-upload (handles user=None).
- **Common**: All inherit `BaseModel`; uses `parse_resume_ai` (strict prompt against hallucination), CSV utils, threaded decorators.
- **Clients**: Via Job → Application → ClientSubmission.

**Notes**: 
- Querysets for visibility: `Q(applications__isnull=True)` for pool candidates.
- `CalendarEventsView` updated to filter on Application/InterviewSchedule.
- Hardened AI parsing with dedicated error JSON path.
- Soft-delete via BaseModel; no hard deletes.

