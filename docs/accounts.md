# Accounts Module Documentation

## Overview
Handles authentication, multi-tenant user management (scoped to `Organization`), role-based dashboards, profile, and organization registration.

**Key Models**: 
- `Organization` (tenant root with UUID PK)
- `User` (extends AbstractBaseUser, has `organization = ForeignKey(Organization)`, `created_by`, `role`)
- Uses custom manager and UUID PKs for consistency.

## Flow Diagram - Accounts Module

```mermaid
flowchart TD
    R[Register Organization<br/>POST /auth/register/] --> A[Login]
    A[Login] --> B{Valid Credentials?}
    B -->|Yes| C[Return JWT Tokens + User Info]
    B -->|No| D[Error 401]
    C --> E[Access Dashboard based on Role]
    E --> F[User Management<br/>(Singular /users/ API - role in payload)]
    F --> G[Profile Management<br/>GET/PATCH /auth/me/]
    G --> H[Logout]
    
    subgraph Dashboards
    I[Admin Dashboard<br/>Stats + Recent Activity]
    J[Manager Dashboard<br/>My Jobs + Pipeline]
    K[Recruiter Dashboard<br/>Assigned Jobs + Interviews]
    end
    E --> I & J & K
```

## Key APIs

### 1. Login
- **Endpoint**: `POST /api/v1/auth/login/`
- **Example with seeded data** (use one of the org-scoped accounts):
  ```json
  {
    "email": "admin@techsolutions.com",
    "password": "admin123"
  }
  ```
  or
  ```json
  {
    "email": "admin@globalcorp.com",
    "password": "admin123"
  }
  ```
- **Success Response (200)**:
  ```json
  {
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "user": {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Raj Admin",
      "email": "admin@techsolutions.com",
      "role": "admin",
      "organization": "Tech Solutions",
      "avatar": null
    }
  }
  ```

**Multi-Tenancy Note**: All users are scoped to an `Organization`. Login returns org context; all subsequent API calls are filtered to the user's organization via custom querysets and middleware.

### 2. Refresh Token
- **Endpoint**: `POST /api/v1/auth/token/refresh/`
- **Body**: `{"refresh": "refresh.token.here"}`
- **Response**: New access token.

### 3. Logout
- **Endpoint**: `POST /api/v1/auth/logout/`
- **Body**: `{"refresh": "refresh.token.here"}`
- **Headers**: Authorization: Bearer <access>
- **Response**: 205 Reset Content

### 4. Forgot Password
- **Endpoint**: `POST /api/v1/auth/forgot-password/`
- **Body**: `{"email": "user@example.com"}`
- **Response**: `{"message": "If an account with that email exists, we have sent a password reset link."}`

### 5. Me (Profile)
- **Endpoint**: `GET /api/v1/auth/me/`
- **Response**: User details
- **PATCH**: Update name, phone, avatar.

### 6. User Management
- **Singular User API**: `POST /api/v1/users/` (replaces separate managers/recruiters endpoints)
  - **Body** (include `role`):
    ```json
    {
      "role": "manager",
      "name": "Manager Name",
      "email": "manager@example.com",
      "phone": "9876543210",
      "password": "pass123"
    }
    ```
    or for recruiter:
    ```json
    {
      "role": "recruiter",
      "name": "Recruiter Name",
      "email": "recruiter@example.com",
      "phone": "9876543210",
      "password": "pass123"
    }
    ```
  - **Permissions**: 
    - Admin can create both `manager` and `recruiter`.
    - Manager can only create `recruiter`.
  - **List**: `GET /api/v1/users/` - Returns managers (for admins with stats) or recruiters (role-filtered for managers).
  - **Other actions**: GET/PUT/DELETE `/api/v1/users/{id}/` supported with same permissions.
  - Role-based queryset filtering and audit logging applied automatically.

### 7. Organization Registration
- **Endpoint**: `POST /api/v1/auth/register/`
- **Body**:
  ```json
  {
    "org_name": "New Company Inc.",
    "admin_name": "Admin User",
    "admin_email": "admin@newcompany.com",
    "admin_password": "securepass123"
  }
  ```
- **Success Response (201)**: Creates `Organization` + initial `ADMIN` user atomically, returns JWT tokens.
  ```json
  {
    "message": "Organization and admin account created successfully",
    "organization": {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "New Company Inc."
    },
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Admin User",
      "email": "admin@newcompany.com",
      "role": "admin",
      "organization": "New Company Inc."
    },
    "tokens": {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    }
  }
  ```
- Duplicate checks (in serializer + view) prevent re-registration for same org name or admin email. This bootstraps a new tenant with full isolation. Subsequent managers/recruiters created via the `/api/v1/users/` endpoint.

### 8. Dashboards
- `GET /api/v1/dashboard/admin/` - Stats on jobs, candidates, clients, recent activity (org-scoped).
- `GET /api/v1/dashboard/manager/` - My jobs, pipeline, interviews today (org-scoped).
- `GET /api/v1/dashboard/recruiter/` - Assigned jobs, candidates, interviews (org-scoped).

**Permissions**:
- Uses custom permissions: IsAdmin, IsManager, IsRecruiter, IsAdminOrManager.
- All actions logged to Audit module.
- **Multi-tenancy enforced**: Querysets filtered by `request.user.organization`; middleware ensures org context.

## Integration Points
- Used by all other modules for authentication and authorization.
- Created users can be assigned to jobs as recruiters.
- Dashboard data aggregates from Clients, Jobs, Candidates, Audit.
