# Audit Module Documentation

## Overview
Tracks all user actions for compliance, debugging, and activity monitoring. Logs who did what, when, on which entity.

**Key Model**: AuditLog

## Flow Diagram - Audit Logging Process

```mermaid
flowchart TD
    A[User Performs Action<br/>(Create/Update/Delete)] --> B[log_action() Utility Called]
    B --> C[Create AuditLog Entry]
    C --> D[Store in DB<br/>actor, action, target_type, target_id, description]
    D --> E[Dashboard displays Recent Activity]
    E --> F[Admin can query/filter logs<br/>GET /api/v1/audit/logs/]
    F --> G[Export Reports (future)]
    
    subgraph Logged Actions
    H[User Management]
    I[Client CRUD]
    J[Job Create/Update/Status]
    K[Candidate Pipeline Changes]
    L[Interview Schedule]
    end
    A --> H & I & J & K & L
```

## Key APIs

### 1. List Audit Logs
- **Endpoint**: `GET /api/v1/audit/logs/`
- **Query Params**: `?actor=uuid&action=created&target_type=Job&date_from=2024-01-01`
- **Response Example**:
  ```json
  {
    "results": [
      {
        "id": "log-uuid",
        "timestamp": "2024-01-01T10:30:00Z",
        "actor": {
          "id": "user-uuid",
          "name": "Manager Name",
          "role": "manager"
        },
        "action": "created",
        "target_type": "Job",
        "target_id": "job-uuid",
        "description": "Created job 'Senior Python Developer'",
        "ip_address": "192.168.1.1",
        "metadata": {"status": "open"}
      }
    ]
  }
  ```

### 2. Audit Log Detail
- `GET /api/v1/audit/logs/{id}/`

## Audit Utility Usage
In views (example from codebase):
```python
from audit.utils import log_action

# After successful create/update
log_action(
    request.user, 
    'created', 
    'Job', 
    job.id, 
    f"Created job '{job.title}'"
)
```

## Logged Entities
- **Accounts**: User create/delete
- **Clients**: Create, update status, add POC
- **Jobs**: Create, status change, stage management
- **Candidates**: Add, status update, interview schedule, feedback
- **System**: Login attempts (future), permission denials

## Fields in AuditLog
- timestamp
- actor (ForeignKey to User)
- action (created, updated, deleted, status_changed)
- target_type (model name)
- target_id (UUID)
- description (human readable)
- ip_address
- metadata (JSON for extra context)

## Steps for Audit Process
1. **Action Performed**: Any CRUD or status change in the system.
2. **log_action Called**: From views or signals.
3. **Log Created**: Immutable record stored.
4. **Visibility**: Shown in Admin and Manager dashboards as "Recent Activity".
5. **Filtering**: Admins can filter by user, date range, module.
6. **Compliance**: Helps in tracking who changed candidate status or client terms.
7. **Analytics**: Can be used for reports on recruiter activity.

## Integration
- **All Modules**: Uses the shared `audit.utils.log_action()`
- **Accounts**: Links actions to specific users/roles
- **Dashboards**: Recent logs displayed on admin dashboard
- **Notifications**: Critical audit events may trigger notifications

This provides complete traceability from login to final hiring decision.
