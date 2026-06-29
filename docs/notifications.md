# Notifications Module Documentation

## Overview
Handles real-time and email notifications for events like new candidate, interview scheduled, status changes, job assignments.

**Key Features**: Event-driven notifications, user preferences, delivery tracking.

## Flow Diagram - Notification System

```mermaid
flowchart TD
    A[Event Triggered<br/>(e.g. Candidate Added)] --> B[Notification Service]
    B --> C[Determine Recipients<br/>(Recruiter, Manager, Client POC)]
    C --> D[Create Notification Record]
    D --> E[Send Channels<br/>In-App + Email + SMS?]
    E --> F[Mark as Read Tracking]
    F --> G[User Views Notifications<br/>GET /api/v1/notifications/]
    G --> H[Real-time Updates via WebSocket (future)]
    
    subgraph Events
    I[New Candidate]
    J[Interview Scheduled]
    K[Status Changed to Hired]
    L[Job Assigned]
    M[Client Feedback Received]
    end
    A --> I & J & K & L & M
```

## Key APIs

### 1. List Notifications
- **Endpoint**: `GET /api/v1/notifications/`
- **Query Params**: `?unread=true&limit=20`
- **Response**:
  ```json
  {
    "results": [
      {
        "id": "notif-uuid",
        "title": "New Candidate Added",
        "message": "Rahul Sharma applied for Senior Python Developer",
        "type": "candidate_added",
        "is_read": false,
        "created_at": "2024-01-01T10:00:00Z",
        "related_candidate": "cand-uuid",
        "related_job": "job-uuid"
      }
    ],
    "unread_count": 3
  }
  ```

### 2. Mark as Read
- `PATCH /api/v1/notifications/{id}/` or bulk action.
- **Body**: `{"is_read": true}`

### 3. Mark All Read
- `POST /api/v1/notifications/mark-all-read/`

## Notification Types & Triggers
1. **Candidate Related**:
   - New candidate added to job
   - Interview scheduled (with calendar invite)
   - Status changed (to client, hired, rejected)

2. **Job Related**:
   - New job assigned to recruiter
   - Job status changed

3. **Client Related**:
   - New client onboarding
   - Client feedback received

4. **System**:
   - Dashboard alerts
   - Audit critical actions

## Steps for Notification Flow
1. **Event Occurs**: e.g., candidate status updated in Candidates view.
2. **Signal/Handler**: Notifications app listens for model signals or explicit calls.
3. **Generate Notification**: Create record with title, message, recipients.
4. **Delivery**: 
   - In-app notification (stored in DB)
   - Email to involved parties (recruiter, manager, client POC)
5. **User Interaction**: User sees bell icon with unread count, clicks to view list.
6. **Actionable**: Notifications often contain deep links to candidate/job detail.
7. **Archiving**: Old notifications cleaned up periodically.

## Integration Points
- **Candidates**: Major source of events (status changes, interviews).
- **Jobs**: Job assignment and status.
- **Accounts**: Targets users by role and assignment.
- **Audit**: Some critical notifications on audit events.
- **Common**: Uses utils for standardized notification templates.

**Future Enhancements**: WebSocket for real-time, push notifications, configurable preferences per user.
