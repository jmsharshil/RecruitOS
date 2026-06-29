# Documentation Index - Recruitment Management System

## Module-wise Documentation

This directory contains comprehensive documentation for the entire system from **Login to Final Hiring**.

### Core Documents

- **[overall_process.md](./overall_process.md)** - Complete A-to-Z flow with high-level diagram (Login → Client → Job → Candidate Pipeline → Hired → Logout)
- **[accounts.md](./accounts.md)** - Authentication, User Management, Role-based Dashboards
- **[clients.md](./clients.md)** - Client onboarding, POCs, commercial terms
- **[jobs.md](./jobs.md)** - Job requisitions, stages/pipeline setup, recruiter assignment
- **[candidates.md](./candidates.md)** - Core candidate management, interviews, client submissions, status pipeline
- **[notifications.md](./notifications.md)** - Event notifications across the system
- **[audit.md](./audit.md)** - Complete activity logging and compliance
- **[common.md](./common.md)** - Shared base models, permissions, utilities

## How to Use These Docs

1. **Start with overall_process.md** for the big picture and end-to-end flow.
2. Dive into specific modules for detailed API contracts, request/response examples, and Mermaid diagrams.
3. All diagrams use **Mermaid** syntax (renderable in GitHub, VSCode, Markdown viewers).
4. API examples include exact body structures inferred from serializers and views.
5. Follow the numbered steps in each document to understand the sequential process.

## System Overview
This is a **multi-tenant role-based recruitment/ATS (Applicant Tracking System)** with:
- **Multi-Tenancy**: Full data isolation by `Organization`. All core models inherit from `BaseModel` (which adds `organization = ForeignKey(Organization)`). Views, filters, and permissions automatically scope queries to `request.user.organization`.
- **3 User Roles**: Admin, Manager, Recruiter (scoped per organization)
- **Multi-stage candidate pipeline** with dynamic stages per job
- **Client management** with POCs, commercial terms, documents
- **Job requisitions** with recruiter assignments and pipeline stages
- **Comprehensive audit trail** and notification system
- **CSV Export & Import** for Candidates, Clients, and Jobs (organization-scoped)

**Key Models**: `Organization`, `User` (with FK to org), `BaseModel` (in common/models.py) provides automatic tenant FK + timestamps + created_by for all downstream models (Client, Job, Candidate, etc.).

## Export / Import Quick Reference

| Module | Export Endpoint | Import Endpoint | Import Auth |
|---|---|---|---|
| Candidates | `GET /api/v1/candidates/export/` | `POST /api/v1/candidates/import/` | Admin / Manager |
| Clients | `GET /api/v1/clients/export/` | `POST /api/v1/clients/import/` | Admin only |
| Jobs | `GET /api/v1/jobs/export/` | `POST /api/v1/jobs/import/` | Admin / Manager |

- All **export** endpoints are accessible to any authenticated user and return a `.csv` file.
- All **import** endpoints accept a `multipart/form-data` POST with the key `file`.
- Imports return `201` on full success, `207` on partial success, with a row-level `errors` array.

## Typical End-to-End Process
1. **Login** (Accounts)
2. **Create Client** (Clients) — or **Import** from CSV
3. **Post Job** (Jobs) + assign recruiters — or **Import** from CSV
4. **Source Candidates** (Candidates) — or **Import** from CSV
5. **Manage Pipeline** (Interviews → Client Round → Offer → Hire)
6. **Receive Notifications** at each step
7. **Export** data at any point for reporting
8. **All actions Audited**
9. **Logout**

## Demo Data & Multi-Tenant Setup

To quickly populate the system with realistic **multi-tenant** sample data covering all modules, pipeline stages, and 2 isolated organizations:

```bash
python manage.py seed_data
```

This command:
- Clears ALL existing data (in FK-safe order) to support re-running
- Creates **2 Organizations** ("Tech Solutions", "Global Corp")
- Creates **7 scoped Users** (2 Admins, 2 Managers, 3 Recruiters) with proper `created_by` chains and `organization` FKs
- Creates **3 Clients** (2 in Tech Solutions, 1 in Global Corp) + POCs + sample documents
- Creates **6 Jobs** (4 + 2) with auto-generated `Stage`s (using DEFAULT_STAGES), recruiter assignments (org-scoped)
- Creates **15 Candidates** partitioned across orgs/jobs with realistic status → stage mapping, conditional `InterviewSchedule`/`ClientSubmission` objects
- Generates **9 AuditLog** entries and **6 Notifications** (all org-scoped)
- Uses realistic data, random variations, and proper tenant isolation

**Login credentials** (all passwords are `admin123` / `manager123` / `recruiter123` respectively):
- **Tech Solutions**:
  - Admin: `admin@techsolutions.com`
  - Manager: `manager@techsolutions.com`
  - Recruiters: `recruiter@techsolutions.com`, `recruiter2@techsolutions.com`
- **Global Corp**:
  - Admin: `admin@globalcorp.com`
  - Manager: `manager@globalcorp.com`
  - Recruiter: `recruiter@globalcorp.com`

**Recommended after fresh `migrate`**: Run the seed command before starting the dev server. The output will confirm counts per organization.

New organizations can be registered via `POST /api/v1/organizations/register/` (endpoint coming soon).

## Additional Resources
- Check `config/urls.py` for all API endpoints (prefixed with `/api/v1/`).
- All APIs use JWT authentication after login.
- Role-based permissions enforced everywhere.
- Soft deletes used for data integrity.
- Export CSV format is directly compatible with the Import endpoint — export, edit, re-import.

**Generated for**: Complete process documentation with APIs, examples, visual flows, and multi-tenant architecture.

**Multi-Tenancy Notes**: 
- `BaseModel` ensures every record belongs to an `Organization`.
- Custom permissions and queryset filters (e.g. `organization=request.user.organization`) enforce strict isolation.
- Seed data demonstrates full partitioning (no cross-org data leakage).
- Audit and Notifications also scoped to organization.

---
*Last Updated: 2024-10-04*

