# Candidates Module Documentation

## Overview
Core module for managing candidate pipeline from sourcing to hiring. Tracks status, interviews, client submissions, feedback.

**Key Models**: Candidate, InterviewSchedule, ClientSubmission

**Candidate Statuses**: screening, interview-scheduled, sent-to-client, hired, rejected, on-hold

## End-to-End Candidate Flow Diagram

```mermaid
flowchart TD
    A[Sourcing<br/>Add Candidate or Upload Resume] --> B[Screening]
    B --> C[Schedule Interview<br/>POST Interview details]
    C --> D[Interview Completed]
    D --> E[Decision: Move to Next Stage?]
    E -->|Yes| F[Update Current Stage]
    E -->|Client Round| G[Client Submission<br/>sent-to-client status]
    F --> H[Collect Feedback]
    G --> I[Client Feedback Received]
    I --> J{Outcome?}
    J -->|Positive| K[Offer Stage → Hired]
    J -->|Negative| L[Rejected/On-Hold]
    K & L --> M[Update Status & Log]
    M --> N[Notifications to Stakeholders]
    
    style A fill:#bae6fd
    style K fill:#86efac
    style L fill:#fda4af
```

## Key APIs

### 1. Add Candidate
- **Endpoint**: `POST /api/v1/candidates/`
- **Request Body**:
  ```json
  {
    "job": "job-uuid",
    "candidate_name": "Rahul Sharma",
    "profile_name": "Senior Backend Engineer",
    "current_company": "Current Corp",
    "experience": "6 years",
    "current_location": "Bangalore",
    "contact": "9876543210",
    "email": "rahul@example.com",
    "current_ctc": 1500000,
    "expected_ctc": 2200000,
    "notice_period": "30 days",
    "resume": "(file upload)",
    "feedback": "Strong Python background"
  }
  ```
- **Response**: Candidate created with ID, status=screening, current_stage=first stage.

### 2. List Candidates
- `GET /api/v1/candidates/?job=job-id&status=screening`
- Supports filtering by job, status, stage.

### 3. Candidate Detail & Update
- `GET/PATCH /api/v1/candidates/{id}/`
- Update status, feedback, move stages.

### 4. Schedule Interview
- Part of candidate update or dedicated.
- **Example Body**:
  ```json
  {
    "date": "2024-01-15",
    "time": "14:30:00",
    "mode": "online",
    "interviewer_name": "Tech Lead",
    "notes": "Focus on system design"
  }
  ```

### 5. Client Submission
- When moving to client round:
  - Creates ClientSubmission record.
  - Updates status to `sent-to-client`.

### 7. Calendar Events
- `GET /api/v1/candidates/calendar/events/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- Returns interview schedules and share dates grouped by date.

### 8. Public Resume Upload
- `GET /api/v1/candidates/upload/{job_id}/` — Fetch public job details (no auth required).
- `POST /api/v1/candidates/upload/{job_id}/` — Public endpoint for candidates to self-submit.
  - **Body** (multipart/form-data): `name`, `email`, `phone`, `resume` (file)

### 9. Export Candidates (CSV)
- **Endpoint**: `GET /api/v1/candidates/export/`
- **Auth**: Any authenticated role.
- **Query Params**:
  - `status` — filter by candidate status (e.g. `?status=screening`)
  - `job_id` — filter by a specific job UUID
- **Response**: Streams a `candidates_export.csv` file download.
- **CSV Columns**:
  ```
  candidate_name, profile_name, current_company, current_profile,
  experience, current_location, preferred_location, education,
  college, contact, email, current_ctc, expected_ctc, notice_period,
  status, share_date, feedback, job_title
  ```

### 10. Import Candidates (CSV)
- **Endpoint**: `POST /api/v1/candidates/import/`
- **Auth**: Admin or Manager only.
- **Body** (multipart/form-data): `file` — a `.csv` file.
- **Required CSV Columns**: `candidate_name`, `email`, `contact`, `job_title`
- **Duplicate Handling**: Skips rows where a candidate with the same `email` already exists for the same job.
- **Response (201)** — all rows imported:
  ```json
  { "created": 10, "skipped": 0, "errors": [] }
  ```
- **Response (207)** — partial success:
  ```json
  {
    "created": 8,
    "skipped": 2,
    "errors": [
      { "row": 3, "error": "Job 'Unknown Job' not found." },
      { "row": 7, "error": "Candidate with email 'a@b.com' already exists for this job." }
    ]
  }
  ```

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template, fill in new rows, and re-upload via **Import**.

## Pipeline Steps (Detailed)
1. **Sourcing**: Recruiter adds candidate or candidate uploads via shared link.
2. **Screening**: Review resume, initial feedback.
3. **Interview Scheduling**: Set date/time/mode, notify all parties.
4. **Round Progression**: Update current_stage after each round with feedback.
5. **Client Submission**: Send profile to client with details.
6. **Client Feedback**: Update with client_rating, client_feedback.
7. **Offer/Negotiation**: Move to offer stage, discuss CTC.
8. **Final Status**: HIRED (update records) or REJECTED with reason.
9. **Documentation**: All changes create AuditLog entries.

## Sample Response for Candidate
```json
{
  "id": "cand-uuid",
  "job": "job-uuid",
  "candidate_name": "Rahul Sharma",
  "status": "interview-scheduled",
  "current_stage": {"name": "Technical", "order": 3},
  "interview_schedule": {
    "date": "2024-01-15",
    "time": "14:30:00",
    "mode": "online"
  },
  "feedback": "Good problem solving skills",
  "resume_file_name": "rahul_resume.pdf"
}
```

## Integration
- **Jobs**: Candidates belong to a Job with its stages.
- **Accounts**: Created_by recruiter, interviewers from users.
- **Notifications**: Interview reminders, status change alerts.
- **Audit**: Every status update, interview schedule, export and import logged.
- **Common**: Uses BaseModel for timestamps, soft deletes.

**Note**: Soft delete (is_deleted flag) used instead of hard delete for compliance.

