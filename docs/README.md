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

## Typical End-to-End Process
1. **Login** (Accounts)
2. **Create Client** (Clients)
3. **Post Job** (Jobs) + assign recruiters
4. **Source Candidates** (Candidates)
5. **Manage Pipeline** (Interviews → Client Round → Offer → Hire)
6. **Receive Notifications** at each step
7. **All actions Audited**
8. **Logout**

## Additional Resources
- Check `config/urls.py` for all API endpoints (prefixed with `/api/v1/`)
- All APIs use JWT authentication after login
- Role-based permissions enforced everywhere
- Soft deletes used for data integrity

**Generated for**: Complete process documentation with APIs, examples, and visual flows.

---
*Last Updated: Auto-generated via AI coding assistant*
