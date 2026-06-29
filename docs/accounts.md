# Accounts Module Documentation

## Overview
Handles authentication, multi-tenant user management (scoped to `Organization`), role-based dashboards, profile, and organization registration (planned).

**Key Models**: 
- `Organization` (tenant root)
- `User` (extends AbstractBaseUser, has `organization = ForeignKey(Organization)`, `created_by`, `role`)
- Uses `BaseModel` inheritance pattern for consistency across system.

## Flow Diagram - Accounts Module

```mermaid
flowchart TD
    A[Login] --> B{Valid Credentials?}
    B -->|Yes| C[Return JWT Tokens + User Info]
    B -->|No| D[Error 401]
    C --> E[Access Dashboard based on Role]
    E --> F[User Management<br/>(Admin creates Managers, Managers create Recruiters)]
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
- **Create Manager**: `POST /api/v1/managers/`
  - **Body**:
    ```json
    {
      "name": "Manager Name",
      "email": "manager@example.com",
      "phone": "9876543210",
      "password": "pass123"
    }
    ```
  - Requires Admin role.

- **Create Recruiter**: `POST /api/v1/recruiters/`
  - Similar body, requires Admin or Manager.

- **List/View**: GET endpoints with role-based filtering.

### 7. Organization Registration (Planned)
- **Endpoint**: `POST /api/v1/organizations/register/`
- **Body**:
  ```json
  {
    "name": "New Company Inc.",
    "admin_email": "admin@newcompany.com",
    "admin_name": "Admin User",
    "admin_password": "securepass123",
    "industry": "IT Services"
  }
  ```
- **Response**: Creates `Organization` + initial `ADMIN` user, returns tokens.
- This will bootstrap a new tenant with full isolation.

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
