# Jobs Module Documentation

## Overview
Manages job requisitions/positions. Linked to clients, assigned to recruiters, with multi-stage pipeline.

**Key Models**: Job, Stage

**Statuses**: open, closed, on-hold

**Hiring For**: self or client

## Flow Diagram - Job Creation to Pipeline Setup

```mermaid
flowchart TD
    A[Client Created] --> B[Create Job<br/>POST /api/v1/jobs/]
    B --> C[Auto-create Default Stages<br/>Screening → Technical → Client Round → Offer → Hired]
    C --> D[Assign Recruiters<br/>Many-to-Many]
    D --> E[Share Resume Upload Link]
    E --> F[Recruiters Add Candidates]
    F --> G[Monitor Pipeline per Stage]
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

### 1. Create Job
- **Endpoint**: `POST /api/v1/jobs/`
- **Request Body**:
  ```json
  {
    "title": "Senior Python Developer",
    "description": "Looking for experienced Django developer...",
    "skills": ["Python", "Django", "REST API", "PostgreSQL"],
    "experience": "4-7 years",
    "location": "Mumbai (Hybrid)",
    "hiring_for": "client",
    "client": "client-uuid",
    "assigned_recruiters": ["recruiter-uuid-1", "recruiter-uuid-2"]
  }
  ```
- **Response (201)**: Job object with ID, auto-generated resume_upload_link, and default stages created.

### 2. List Jobs
- **Endpoint**: `GET /api/v1/jobs/`
- Role-based filtering:
  - Admin: All jobs
  - Manager: Jobs created by them
  - Recruiter: Jobs assigned to them
- Supports filtering by status, client, etc.

### 3. Job Detail
- `GET /api/v1/jobs/{id}/` - Includes stages and candidate counts per stage.

### 4. Update Job Status
- **Endpoint**: `PATCH /api/v1/jobs/{id}/status/`
- **Body**: `{"status": "closed"}`
- **Response**: `{"status": "closed"}`

### 5. Manage Stages
- `POST /api/v1/jobs/{id}/stages/` - Add custom stage
- `PATCH /api/v1/jobs/{id}/stages/{stage_id}/` - Update stage
- `DELETE /api/v1/jobs/{id}/stages/{stage_id}/` - Remove (if no candidates)

### 6. Get Upload Link
- `GET /api/v1/jobs/{id}/upload-link/`
- Returns public link for candidates to upload resumes.

### 7. Export Jobs (CSV)
- **Endpoint**: `GET /api/v1/jobs/export/`
- **Auth**: Any authenticated role (results are role-scoped).
- **Query Params**: `status` — filter by job status (e.g. `?status=open`)
- **Response**: Streams a `jobs_export.csv` file download.
- **CSV Columns**:
  ```
  title, experience, location, hiring_for,
  client_name, status, skills, description
  ```

### 8. Import Jobs (CSV)
- **Endpoint**: `POST /api/v1/jobs/import/`
- **Auth**: Admin or Manager only.
- **Body** (multipart/form-data): `file` — a `.csv` file.
- **Required CSV Columns**: `title`, `experience`, `location`
- **Notes**:
  - `client_name` is matched case-insensitively to an existing active client.
  - `skills` should be a comma-separated string: `"Python, Django, REST API"`.
  - If `client_name` is provided but not found, the job is still created (without a client) and an error note is included.
- **Response (201)** — all rows imported:
  ```json
  { "created": 3, "skipped": 0, "errors": [] }
  ```
- **Response (207)** — partial success:
  ```json
  {
    "created": 2,
    "skipped": 0,
    "errors": [
      { "row": 4, "error": "Client 'Unknown Corp' not found. Job will be created without a client." }
    ]
  }
  ```

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template, fill in new rows, and re-upload via **Import**.

## Steps in Job Lifecycle
1. **Creation**: Manager/Admin creates job linked to client, assigns recruiters.
2. **Stage Setup**: Default 6 stages created automatically.
3. **Distribution**: Recruiters get notified of new job assignment.
4. **Sourcing**: Recruiters use the upload link or add candidates manually.
5. **Monitoring**: Track candidates per stage via dashboard.
6. **Closure**: Update status to closed when fulfilled or on-hold.

## API Response Example (Job List Item)
```json
{
  "id": "job-uuid",
  "title": "Senior Python Developer",
  "client": {"company_name": "Tech Corp"},
  "status": "open",
  "assigned_recruiters": [...],
  "stages": [...],
  "candidate_counts": {
    "screening": 5,
    "interview-scheduled": 3,
    "hired": 1
  }
}
```

## Integration Points
- **Clients**: One-to-Many (Client can have multiple jobs)
- **Accounts**: Recruiters assigned via M2M
- **Candidates**: Jobs have many candidates progressing through stages
- **Notifications**: New job, stage changes, candidate updates
- **Audit**: All job CRUD, status changes, exports and imports logged

**Common Stages**: Screening, HR Round, Technical, Client Round, Offer, Hired.

