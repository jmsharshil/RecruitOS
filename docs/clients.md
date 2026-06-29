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

### 7. Export Clients (CSV)
- **Endpoint**: `GET /api/v1/clients/export/`
- **Auth**: Any authenticated role.
- **Query Params**: `status` — filter by client status (e.g. `?status=active`)
- **Response**: Streams a `clients_export.csv` file download.
- **CSV Columns**:
  ```
  client_id, company_name, client_name, email, contact,
  industry, city, state, country, status,
  website, gst_number, agreement_date, payment_period_days, replacement_period_days
  ```

### 8. Import Clients (CSV)
- **Endpoint**: `POST /api/v1/clients/import/`
- **Auth**: Admin only.
- **Body** (multipart/form-data): `file` — a `.csv` file.
- **Required CSV Columns**: `company_name`, `client_name`, `email`, `contact`, `industry`
- **Duplicate Handling**: Skips rows where a client with the same `email` already exists (non-deleted).
- **Response (201)** — all rows imported:
  ```json
  { "created": 5, "skipped": 0, "errors": [] }
  ```
- **Response (207)** — partial success:
  ```json
  {
    "created": 4,
    "skipped": 1,
    "errors": [
      { "row": 3, "error": "Client with email 'hr@abc.com' already exists." }
    ]
  }
  ```

> [!TIP]
> Use the **Export** endpoint to download a correctly formatted template, fill in new rows, and re-upload via **Import**.

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
- Only Admin can bulk-import clients.

## Integration
- **Jobs**: Every job links to a Client.
- **Candidates**: Client feedback flows back to client POCs via notifications.
- **Audit**: All client actions (create, update, delete, export, import) are audited.
- **Notifications**: New client onboarding triggers alerts.

**Note**: Client ID is auto-generated (CLI-0001 format).

