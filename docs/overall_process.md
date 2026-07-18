# Overall A to Z Process - ATS

## End-to-End Flow from Login to Final Hiring

This document describes the complete process from user login to candidate hiring/rejection, covering all modules.

### High-Level Flow Diagram (Updated with Application Decoupling)

```mermaid
flowchart TD
    A[1. User Login<br/>POST /api/v1/auth/login/] --> B[2. Role-based Dashboard<br/>GET /api/v1/dashboard/{role}/]
    B --> C[3. Client Management<br/>(Admin/Manager)<br/>CRUD Clients]
    C --> D[4. Job Creation<br/>POST /api/v1/jobs/<br/>Auto-create stages]
    D --> E[5. Assign Recruiters to Job]
    E --> F[6. Candidate Sourcing<br/>POST /api/v1/candidates/ or PublicUpload (AI parse)]
    F --> G[7. Application Join Model<br/>(Candidate ↔ Job; pool has none)]
    G --> H[8. Pipeline Mgmt (status/stage on Application)]
    H --> I[9. InterviewSchedule + ClientSubmission (link to Application)]
    I --> J[10. Feedback, Status Updates (Hired/Rejected)]
    J --> K[11. Threaded Notifications (Application-first, pool fallback)]
    K --> L[12. Audit (log_action w/ user=None support)]
    L --> M[Final: Hired or Rejected]
    M --> N[Logout<br/>POST /api/v1/auth/logout/]
    
    style A fill:#4ade80
    style M fill:#4ade80
    style G fill:#67e8f9
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
   - Recruiters add to talent pool (`Candidate`) or create `Application` linked to Job.
   - Public upload (`PublicUploadView`, AllowAny) does strict AI resume parse (`parse_resume_ai` + task) then creates Candidate + Application.
   - Pool candidates have no Application; job-linked use Application for status/stage/feedback.
   - Initial status: screening (on Application).
   - See `docs/candidates.md` for full details on decoupled models, RBAC Q-filters, CSV, etc.

6. **Pipeline Progression**
   - Update `Application.current_stage`, status, feedback.
   - Schedule `InterviewSchedule` (linked to Application).
   - Client submission creates `ClientSubmission` linked to Application.
   - Collect feedback; notifications thread-safe with Application-first lookup + pool fallback.

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

- **Accounts** → Authenticates all actions, provides UserRole, Organization
- **Clients** → Foundation for Jobs
- **Jobs** → Links to Candidates **via Application join model** (with stages)
- **Candidates** → Talent pool (`Candidate`) + linkage (`Application`), AI parsing, CSV, PublicUploadView, CalendarEventsView (updated), ViewSets with Q-filter querysets + perform_create hooks
- **Notifications** → Event-driven (threaded decorators, simulate_* functions updated for Application fallback)
- **Audit** → Compliance (log_action extended for user=None/public uploads)
- **Common** → `BaseModel` (org + soft-delete for *all* models), permissions, utils (CSV, safe_float, etc.)

### Authentication Flow
All APIs after login require `Authorization: Bearer <access_token>` header.

### Error Handling
- 401: Unauthorized
- 403: Permission denied (role-based)
- 400: Validation errors with field_errors

For module-specific details, API bodies, responses, and diagrams, refer to the respective MD files in this directory.
