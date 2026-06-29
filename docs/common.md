# Common Module Documentation

## Overview
Shared utilities, base models (`BaseModel` with `organization` FK for multi-tenancy), permissions, and helper functions used across all modules.

**Key Components**:
- `BaseModel` (adds `organization`, `created_at`, `updated_at` to all models)
- Custom Permissions (role-based + org-scoped)
- Utils for audit logging, notifications, filters
- Ensures **strict tenant isolation** - no cross-organization data visibility.

## Base Model (Multi-Tenancy Core)

```mermaid
flowchart TD
    A[All Models Inherit from BaseModel] --> B[Automatic Fields]
    B --> C[organization = ForeignKey(Organization, on_delete=CASCADE)]
    C --> D[created_at, updated_at (auto)]
    D --> E[Automatic tenant filtering in views/querysets]
    E --> F[Strict data isolation between organizations]
```

**Current Implementation** (`common/models.py`):
```python
class BaseModel(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

## Key Features

### 1. Permissions
- `IsAdmin`, `IsManager`, `IsRecruiter`
- `IsAdminOrManager`
- Used in all ViewSets and APIViews
- Example from accounts/views.py:
  ```python
  permission_classes = [IsAdminOrManager]
  ```

### 2. BaseModel (common/models.py)
All tenant models (Client, Job, Candidate, InterviewSchedule, ClientSubmission, POC, ClientDocument, Stage, AuditLog, Notification) inherit from `BaseModel`, which injects the `organization` FK automatically. Some models (e.g. Candidate, Client) additionally implement soft-delete fields (`is_deleted`, `deleted_at`) for data retention.

### 3. Utilities
- `audit.utils.log_action(user, action, target_type, target_id, description)`
- Notification helpers
- Permission mixins

## Role-Based + Multi-Tenant Access Control Flow
1. User logs in with role (from accounts.UserRole) + `organization` context
2. JWT token includes user info; middleware/permissions attach `request.user.organization`
3. Permission classes check `request.user.role` **AND** filter all querysets by `organization=request.user.organization`
4. **Admin**: Full access within their org (create managers, recruiters, clients, jobs)
5. **Manager**: Manage their recruiters, jobs, candidates, clients within org
6. **Recruiter**: Limited to jobs they are assigned to + their candidates (org-scoped)

All views inherit from org-aware base views or use `get_queryset()` overrides that enforce `organization=self.request.user.organization`.

## Shared Components Used in A-Z Process
- **Login to Dashboard**: Base auth, org context, permissions
- **Client/Job/Candidate Creation**: `BaseModel` automatically injects `organization` + `created_by` + timestamps
- **Candidate Pipeline**: Status + Stage mapping, org-scoped InterviewSchedule/ClientSubmission
- **All Actions**: Routed through audit logging utility (also org-scoped)
- **Error Responses**: Standardized validation error format with `field_errors`
- **Tenant Isolation**: Queryset filters + permission checks prevent any cross-org data access

## API Response Patterns (Common)
**Success**:
- 200/201 with data
- Consistent pagination using DRF

**Error**:
```json
{
  "error": "Validation failed",
  "field_errors": {
    "email": ["This field is required."],
    "password": ["Password too short."]
  }
}
```

This module ensures consistency across the entire application from authentication to final candidate status updates.
