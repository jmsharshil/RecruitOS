# Overall A to Z Process - ATS

## End-to-End Flow from Login to Final Hiring

This document describes the complete process from user login to candidate hiring/rejection, covering all modules.

### High-Level Flow Diagram

```mermaid
flowchart TD
    A[1. User Login<br/>POST /api/v1/auth/login/] --> B[2. Role-based Dashboard<br/>GET /api/v1/dashboard/{role}/]
    B --> C[3. Client Management<br/>(Admin/Manager)<br/>CRUD Clients]
    C --> D[4. Job Creation<br/>POST /api/v1/jobs/<br/>Auto-create stages]
    D --> E[5. Assign Recruiters to Job]
    E --> F[6. Candidate Sourcing<br/>POST /api/v1/candidates/<br/>or Public Upload]
    F --> G[7. Candidate Pipeline Management<br/>Update Status, Schedule Interviews]
    G --> H[8. Interview Scheduling<br/>POST InterviewSchedule]
    H --> I[9. Client Submission<br/>Move to Client Round]
    I --> J[10. Feedback & Status Updates<br/>Hired/Rejected/On-Hold]
    J --> K[11. Notifications Sent<br/>Real-time updates]
    K --> L[12. Audit Logging<br/>All actions tracked]
    L --> M[Final: Hired Candidate<br/>or Rejected]
    M --> N[Logout<br/>POST /api/v1/auth/logout/]
    
    style A fill:#4ade80
    style M fill:#4ade80
```

### Step-by-Step Process (A to Z)

1. **Login (Accounts Module)**
   - **API**: `POST /api/v1/auth/login/`
   - **Request Body**:
     ```json
     {
       "email": "recruiter@example.com",
       "password": "password123"
     }
     ```
   - **Response**:
     ```json
     {
       "access": "jwt.token.here",
       "refresh": "refresh.token.here",
       "user": {
         "id": "uuid",
         "name": "John Doe",
         "email": "recruiter@example.com",
         "role": "recruiter",
         "avatar": null
       }
     }
     ```

2. **View Dashboard**
   - Different endpoints based on role (admin/manager/recruiter)
   - Provides stats, recent jobs, pipeline info.

3. **Client Management (Clients Module)**
   - Create client with company details, POC, documents.
   - **API Example**: `POST /api/v1/clients/`
   - See `docs/clients.md` for details.

4. **Job Requisition Creation (Jobs Module)**
   - Create job linked to client, assign recruiters, define skills, experience.
   - Auto-generates pipeline stages (Screening → HR → Technical → Client → Offer → Hired).
   - **API**: `POST /api/v1/jobs/`
   - See `docs/jobs.md`.

5. **Candidate Addition (Candidates Module)**
   - Recruiters add candidates to specific jobs with resume, details.
   - Or use public upload link.
   - Initial status: Screening.
   - See `docs/candidates.md`.

6. **Pipeline Progression**
   - Update candidate current_stage and status.
   - Schedule interviews with date, time, mode.
   - Send to client for review.
   - Collect feedback at each stage.

7. **Interview & Feedback Loop**
   - **API for Interview**: Part of candidate update or dedicated endpoint.
   - Update feedback, ratings, move to next stage.

8. **Notifications (Notifications Module)**
   - Triggered on status changes, interview schedules, new candidates.
   - See `docs/notifications.md`.

9. **Audit Trail (Audit Module)**
   - All CRUD operations logged with actor, action, target.
   - See `docs/audit.md`.

10. **Final Steps**
    - Candidate reaches HIRED or REJECTED status.
    - Update client commercial terms if needed.
    - Generate reports (future extension).
    - Logout.

### Module Interactions

- **Accounts** → Authenticates all actions
- **Clients** → Foundation for Jobs
- **Jobs** → Links to Candidates via stages
- **Candidates** → Core pipeline management
- **Notifications** → Event-driven updates
- **Audit** → Compliance and tracking
- **Common** → Base models, permissions, utils

### Authentication Flow
All APIs after login require `Authorization: Bearer <access_token>` header.

### Error Handling
- 401: Unauthorized
- 403: Permission denied (role-based)
- 400: Validation errors with field_errors

For module-specific details, API bodies, responses, and diagrams, refer to the respective MD files in this directory.
