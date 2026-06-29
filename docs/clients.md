# Clients Module Documentation

## Overview
Manages client/companies that post job requirements. Includes company details, POCs (Points of Contact), documents, and commercial terms.

**Key Models**: Client, ClientDocument, POC

**Statuses**: active, inactive, on-hold

## Flow Diagram - Client Onboarding to Job Posting

```mermaid
flowchart TD
    A[Admin/Manager Login] --> B[Create Client<br/>POST /api/v1/clients/]
    B --> C[Add POCs<br/>(Hiring & Payment)]
    C --> D[Upload Documents<br/>(Agreements, etc.)]
    D --> E[Update Commercial Terms<br/>Payment days, Replacement policy]
    E --> F[Client marked ACTIVE]
    F --> G[Create Job for this Client<br/>Jobs Module]
    G --> H[Monitor Jobs & Candidates]
    
    style A fill:#60a5fa
    style H fill:#4ade80
```

## Key APIs

### 1. Create Client
- **Endpoint**: `POST /api/v1/clients/`
- **Request Body**:
  ```json
  {
    "company_name": "Tech Corp Inc.",
    "client_name": "Jane Smith",
    "email": "jane@techcorp.com",
    "contact": "9876543210",
    "city": "Mumbai",
    "state": "Maharashtra",
    "country": "India",
    "industry": "IT Services",
    "status": "active",
    "payment_period_days": 30,
    "replacement_period_days": 90,
    "pocs": [
      {
        "poc_type": "hiring",
        "name": "Hiring Manager",
        "email": "hiring@techcorp.com",
        "designation": "Talent Acquisition Head",
        "contact": "9123456789"
      }
    ]
  }
  ```
- **Response (201)**:
  ```json
  {
    "id": "uuid-here",
    "client_id": "CLI-0001",
    "company_name": "Tech Corp Inc.",
    "status": "active",
    "created_at": "2024-01-01T10:00:00Z",
    "created_by": "admin-uuid"
  }
  ```

### 2. List Clients
- **Endpoint**: `GET /api/v1/clients/`
- **Query Params**: `?status=active&search=tech`
- **Response**: Paginated list with stats.

### 3. Client Detail
- `GET /api/v1/clients/{id}/`
- Includes related POCs and documents.

### 4. Update Client
- `PATCH /api/v1/clients/{id}/`
- Can update status, commercial terms, etc.

### 5. Add Document
- Related to ClientDocument model via nested serializers or separate endpoint.
- File upload for agreements, NDAs.

### 6. Add/Update POC
- Nested in client create or separate endpoints for POC CRUD.

## Steps in Client Lifecycle
1. **Onboarding**: Admin/Manager creates client record with all details.
2. **POC Setup**: Add hiring manager and payment POC.
3. **Agreement**: Upload signed agreements, set payment/replacement terms.
4. **Activation**: Set status to ACTIVE.
5. **Job Posting**: Client can now have multiple jobs created against it.
6. **Maintenance**: Update contact info, status changes logged in Audit.
7. **Reporting**: Track all candidates submitted to this client.

## Permissions
- Admin and Managers can create/edit clients.
- Recruiters can view clients associated with their jobs.

## Integration
- **Jobs**: Every job links to a Client.
- **Candidates**: Client feedback flows back to client POCs via notifications.
- **Audit**: All client actions (create, update, delete) are audited.
- **Notifications**: New client onboarding triggers alerts.

**Note**: Client ID is auto-generated (CLI-0001 format).
