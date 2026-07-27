# Common Module Documentation

## Overview
Shared utilities, base models (`BaseModel` with `organization` FK, soft-delete support for multi-tenancy), permissions, CSV utils, and helper functions used across all modules.

**Key Components**:
- `BaseModel` (adds `organization`, timestamps, `is_deleted`/`deleted_at` for soft-delete to all models)
- Custom Permissions (role-based + org-scoped)
- Utils for audit logging, notifications, CSV export/import, AI resume parsing
- Ensures **strict tenant isolation** - no cross-organization data visibility. All querysets filter by `organization` + `is_deleted=False`.

## Base Model (Multi-Tenancy + Soft Delete Core)

```mermaid
flowchart TD
    A[All Models Inherit from BaseModel] --> B[Automatic Fields]
    B --> C[organization FK + timestamps]
    C --> D[is_deleted + deleted_at for soft-delete]
    D --> E[Automatic tenant + soft-delete filtering in views/querysets (Q filters)]
    E --> F[Strict data isolation between organizations]
```

**Current Implementation** (`common/models.py`):
```python
class BaseModel(models.Model):
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='%(class)s_related'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

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
All models (Client, Job, Candidate, Application, InterviewSchedule, ClientSubmission, POC, ClientDocument, Stage, AuditLog, Notification, etc.) inherit from `BaseModel`. This provides `organization` scoping, timestamps, and soft-delete (`is_deleted`, `deleted_at`) support. `perform_destroy` in ViewSets typically sets `is_deleted=True` + `deleted_at` instead of hard delete. Querysets use `is_deleted=False` + org filter (often with Q() for pool visibility).

### 3. Utilities
- `audit.utils.log_action(user=None, action, target_type, target_id, description, organization=None)` — supports `user=None` for public uploads/TalentPoolPublicUploadView (defaults user_name='System', explicit org)
- `candidates.utils` (`parse_resume_ai()` with strict anti-hallucination JSON-only prompt + safe defaults, `safe_float()`, `_find_existing_candidate()` for dedup)
- **Unified CSV/Excel** (`utils_csv.py`): `generate_csv_response(filename, headers, rows, export_format='csv')` — supports ?format=xlsx via openpyxl.Workbook (cleans None/bool/date, sets correct content-type/filename); `parse_csv_from_request(request, required_fields=None)` — Excel-first with `openpyxl.load_workbook(..., data_only=True)`, header `normalize_header()` (regex to snake_case), DictReader for CSV (utf-8-sig), row skipping, required validation; `get_choice(val, choices, default)` (case-insens match on value or display label)
- `common/serializers.py`: `DateParserField` (uses `dateutil.parser.parse(fuzzy=True)` + explicit format fallbacks, helpful ValidationError msgs for imports)
- Notification helpers (threaded via `@run_in_thread`)
- `common.permissions`, `custom_exception_handler` (normalized { "error", "detail", "field_errors" } contract used by all views for consistent 4xx/5xx)

## Role-Based + Multi-Tenant Access Control Flow
1. User logs in with role (from accounts.UserRole) + `organization` context
2. JWT token includes user info; middleware/permissions attach `request.user.organization`
3. Permission classes check `request.user.role` **AND** filter all querysets by `organization=request.user.organization`
4. **Admin**: Full access within their org (create managers, recruiters, clients, jobs)
5. **Manager**: Manage their recruiters, jobs, candidates, clients within org
6. **Recruiter**: Limited to jobs they are assigned to + pool candidates (via `Q(applications__isnull=True) | Q(applications__job__assigned_recruiters=user)` filters, org-scoped)

All views use `get_queryset()` overrides with `Q()` filters for Application-linked candidates vs pure talent-pool, enforcing `organization=self.request.user.organization` + `is_deleted=False`.

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
