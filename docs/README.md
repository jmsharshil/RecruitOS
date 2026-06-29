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
This is a **role-based recruitment/ATS (Applicant Tracking System)** with:
- **3 User Roles**: Admin, Manager, Recruiter
- **Multi-stage candidate pipeline**
- **Client management with POCs and commercials**
- **Comprehensive audit trail**
- **Notification system**
- **CSV Export & Import** for Candidates, Clients, and Jobs

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

## Demo Data

To quickly populate the system with realistic sample data covering all modules and pipeline stages:

```bash
python manage.py seed_data
```

This command:
- Clears any existing demo records
- Creates 6 users (Admin: `admin@recruitsmart.com` / password `admin123`; Managers & Recruiters with `manager123`/`recruiter123`)
- Creates 3 clients (TCS, Infosys, Wipro) with POCs and commercial documents
- Creates 6 jobs with auto-generated pipeline stages and recruiter assignments
- Creates 15 candidates distributed across all pipeline stages (Screening → Interview → Client Round → Hired/Rejected)
- Generates sample Audit Logs and Notifications
- Uses realistic Indian names, skills, salary ranges, and feedback

**Recommended after fresh `migrate`**: Run the seed command before starting the dev server.

## Additional Resources
- Check `config/urls.py` for all API endpoints (prefixed with `/api/v1/`).
- All APIs use JWT authentication after login.
- Role-based permissions enforced everywhere.
- Soft deletes used for data integrity.
- Export CSV format is directly compatible with the Import endpoint — export, edit, re-import.

**Generated for**: Complete process documentation with APIs, examples, and visual flows.

---
*Last Updated: 2026-06-29*

