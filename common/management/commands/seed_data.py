from django.core.management.base import BaseCommand
import random
from decimal import Decimal
from datetime import date, timedelta, time
from django.utils import timezone
from django.core.files.base import ContentFile

from accounts.models import User, UserRole, Organization
from clients.models import Client, POC, POCType, ClientStatus, ClientDocument
from jobs.models import Job, Stage, HiringFor, JobStatus, DEFAULT_STAGES
from candidates.models import (
    Candidate, Application, CandidateStatus, InterviewSchedule, InterviewMode,
    ClientSubmission, SubmissionStatus
)
from audit.models import AuditLog, AuditActionType
from notifications.models import Notification, NotificationType


class Command(BaseCommand):
    help = 'Seeds the database with comprehensive demo data for the Recruitment ATS'

    def handle(self, *args, **options):
        self.stdout.write('Clearing existing demo data...')
        
        # Clear existing demo data (including organizations) to allow re-running.
        # Order matters due to FK relationships with CASCADE. Updated for Application decoupling.
        Application.objects.all().delete()
        InterviewSchedule.objects.all().delete()
        ClientSubmission.objects.all().delete()
        Candidate.objects.all().delete()
        Stage.objects.all().delete()
        Job.objects.all().delete()
        POC.objects.all().delete()
        ClientDocument.objects.all().delete()
        Client.objects.all().delete()
        Notification.objects.all().delete()
        AuditLog.objects.all().delete()
        User.objects.all().delete()
        Organization.objects.all().delete()
        
        self.stdout.write('Seeding fresh demo data...')
        
        # 1. Create Organizations (multi-tenant isolation)
        org1 = Organization.objects.create(name="Tech Solutions")
        org2 = Organization.objects.create(name="Global Corp")
        
        # 1b. Create Users scoped to organizations
        admin1 = User.objects.create_superuser(
            email='admin@techsolutions.com',
            name='Raj Admin',
            role=UserRole.ADMIN,
            password='admin123',
            organization=org1
        )
        manager1 = User.objects.create_user(
            email='manager@techsolutions.com',
            name='Priya Manager',
            role=UserRole.MANAGER,
            password='manager123',
            created_by=admin1,
            organization=org1
        )
        recruiter1 = User.objects.create_user(
            email='recruiter@techsolutions.com',
            name='Arjun Recruiter',
            role=UserRole.RECRUITER,
            password='recruiter123',
            created_by=manager1,
            organization=org1
        )
        recruiter2 = User.objects.create_user(
            email='recruiter2@techsolutions.com',
            name='Meera Recruiter',
            role=UserRole.RECRUITER,
            password='recruiter123',
            created_by=manager1,
            organization=org1
        )
        admin2 = User.objects.create_superuser(
            email='admin@globalcorp.com',
            name='Anika Admin',
            role=UserRole.ADMIN,
            password='admin123',
            organization=org2
        )
        manager2 = User.objects.create_user(
            email='manager@globalcorp.com',
            name='Vikram Manager',
            role=UserRole.MANAGER,
            password='manager123',
            created_by=admin2,
            organization=org2
        )
        recruiter3 = User.objects.create_user(
            email='recruiter@globalcorp.com',
            name='Karan Recruiter',
            role=UserRole.RECRUITER,
            password='recruiter123',
            created_by=manager2,
            organization=org2
        )
        
        self.stdout.write('Created 2 organizations and 7 users (2 Admins, 2 Managers, 3 Recruiters)')
        
        # 2. Create Clients with all required fields + POCs + Documents (partitioned across orgs)
        clients_data = [
            {
                'company_name': 'TCS',
                'client_name': 'Ravi Kumar',
                'email': 'ravi.kumar@tcs.com',
                'alternative_email': 'ravi.hr@tcs.com',
                'contact': '+91-9876543210',
                'alternative_contact': '+91-9876543219',
                'website': 'https://www.tcs.com',
                'linkedin': 'https://linkedin.com/company/tcs',
                'street': 'BKC, Bandra Kurla Complex',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'country': 'India',
                'postal_code': '400001',
                'industry': 'IT Services',
                'gst_number': '27AAACT2727Q1Z2',
                'status': ClientStatus.ACTIVE,
                'agreement_date': date(2024, 1, 15),
                'created_by': admin1,
                'payment_period_days': 30,
                'replacement_period_days': 90,
                'commercial_decided': True,
                'organization': org1,
            },
            {
                'company_name': 'Infosys',
                'client_name': 'Sunita Verma',
                'email': 'sunita.verma@infosys.com',
                'alternative_email': 'sunita.ta@infosys.com',
                'contact': '+91-9876543211',
                'alternative_contact': '+91-9876543229',
                'website': 'https://www.infosys.com',
                'linkedin': 'https://linkedin.com/company/infosys',
                'street': 'Electronics City',
                'city': 'Pune',
                'state': 'Maharashtra',
                'country': 'India',
                'postal_code': '411001',
                'industry': 'IT Services & Consulting',
                'gst_number': '29AABCF1234C1Z3',
                'status': ClientStatus.ACTIVE,
                'agreement_date': date(2024, 3, 20),
                'created_by': manager1,
                'payment_period_days': 45,
                'replacement_period_days': 60,
                'commercial_decided': True,
                'organization': org1,
            },
            {
                'company_name': 'Wipro',
                'client_name': 'Amit Singh',
                'email': 'amit.singh@wipro.com',
                'alternative_email': 'amit.hr@wipro.com',
                'contact': '+91-9876543212',
                'alternative_contact': '+91-9876543239',
                'website': 'https://www.wipro.com',
                'linkedin': 'https://linkedin.com/company/wipro',
                'street': 'Sarjapur Road',
                'city': 'Bengaluru',
                'state': 'Karnataka',
                'country': 'India',
                'postal_code': '560001',
                'industry': 'IT Services',
                'gst_number': '29AAACW1234C1Z4',
                'status': ClientStatus.ON_HOLD,
                'agreement_date': None,
                'created_by': manager2,
                'payment_period_days': 30,
                'replacement_period_days': 90,
                'commercial_decided': False,
                'organization': org2,
            },
        ]
        
        created_clients = []
        for data in clients_data:
            client = Client.objects.create(**data)
            created_clients.append(client)
            
            # Create POCs (with org from client)
            POC.objects.create(
                client=client,
                poc_type=POCType.HIRING,
                name=f'{data["client_name"]}',
                email=data['email'],
                designation='Talent Acquisition Head',
                contact=data['contact'],
                description='Primary hiring contact for technical roles.',
                organization=client.organization,
            )
            POC.objects.create(
                client=client,
                poc_type=POCType.PAYMENT,
                name=f'Finance POC - {data["company_name"]}',
                email=f'finance@{data["company_name"].lower()}.com',
                designation='Accounts Manager',
                contact='+91-9876543299',
                description='Handles invoices and payments.',
                organization=client.organization,
            )
            
            # Create dummy ClientDocument (with org)
            doc_content = b'%PDF-1.4\n% Dummy agreement for demo purposes.'
            doc = ClientDocument(
                client=client,
                file_name='commercial_agreement.pdf',
                organization=client.organization,
            )
            doc.file.save('commercial_agreement.pdf', ContentFile(doc_content), save=False)
            doc.save()
        
        tcs, infosys, wipro = created_clients
        self.stdout.write('Created 3 clients (2 in Tech Solutions, 1 in Global Corp) with POCs and documents')
        
        # 3. Create Jobs + Auto Stages (partitioned by org, recruiters from same org)
        jobs_data = [
            {
                'title': 'Senior Python Developer',
                'client': tcs,
                'description': 'Looking for experienced Python developers with strong Django background to work on scalable web applications.',
                'status': JobStatus.OPEN,
                'hiring_for': HiringFor.CLIENT,
                'created_by': manager1,
                'min_experience': 5,
                'max_experience': 8,
                'location': 'Bengaluru, Remote',
                'skills': ['Python', 'Django', 'PostgreSQL', 'AWS', 'REST APIs'],
                'organization': org1,
            },
            {
                'title': 'React Frontend Engineer',
                'client': tcs,
                'description': 'Build modern, responsive UIs using React, Redux and TailwindCSS for our enterprise clients.',
                'status': JobStatus.OPEN,
                'hiring_for': HiringFor.CLIENT,
                'created_by': manager1,
                'min_experience': 3,
                'max_experience': 6,
                'location': 'Mumbai',
                'skills': ['React', 'TypeScript', 'JavaScript', 'Tailwind', 'Redux'],
                'organization': org1,
            },
            {
                'title': 'DevOps Engineer',
                'client': infosys,
                'description': 'Infrastructure automation, CI/CD pipelines, Kubernetes and cloud infrastructure management.',
                'status': JobStatus.OPEN,
                'hiring_for': HiringFor.CLIENT,
                'created_by': manager1,
                'min_experience': 4,
                'max_experience': 7,
                'location': 'Pune, Hybrid',
                'skills': ['AWS', 'Docker', 'Kubernetes', 'Terraform', 'Jenkins'],
                'organization': org1,
            },
            {
                'title': 'Data Analyst',
                'client': infosys,
                'description': 'Analyze business data, create dashboards and provide insights using SQL, Python and BI tools.',
                'status': JobStatus.ON_HOLD,
                'hiring_for': HiringFor.CLIENT,
                'created_by': manager1,
                'min_experience': 2,
                'max_experience': 5,
                'location': 'Pune',
                'skills': ['SQL', 'Python', 'Tableau', 'Excel', 'PowerBI'],
                'organization': org1,
            },
            {
                'title': 'Full Stack Developer (MERN)',
                'client': wipro,
                'description': 'Develop end-to-end features using MongoDB, Express, React and Node.js stack.',
                'status': JobStatus.OPEN,
                'hiring_for': HiringFor.CLIENT,
                'created_by': manager2,
                'min_experience': 4,
                'max_experience': 8,
                'location': 'Bengaluru',
                'skills': ['MongoDB', 'Express', 'React', 'Node.js', 'TypeScript'],
                'organization': org2,
            },
            {
                'title': 'HR Business Partner',
                'client': None,
                'description': 'Internal HR role focusing on talent management, employee engagement and recruitment strategy for our organization.',
                'status': JobStatus.OPEN,
                'hiring_for': HiringFor.SELF,
                'created_by': manager2,
                'min_experience': 7,
                'max_experience': 15,
                'location': 'Mumbai',
                'skills': ['HR Management', 'Recruitment', 'Employee Relations', 'Performance Management'],
                'organization': org2,
            },
        ]
        
        created_jobs = []
        for idx, data in enumerate(jobs_data):
            job = Job.objects.create(**data)
            # Assign recruiters from same organization only
            if job.organization == org1:
                org_recruiters = [recruiter1, recruiter2]
            else:
                org_recruiters = [recruiter3]
            assign_count = min(2 if idx % 3 != 0 else 1, len(org_recruiters))
            job.assigned_recruiters.set(random.sample(org_recruiters, assign_count))
            created_jobs.append(job)
            
            # Create default stages (with organization)
            for stage_data in DEFAULT_STAGES:
                Stage.objects.create(
                    job=job,
                    organization=job.organization,
                    **stage_data
                )
            
        job1, job2, job3, job4, job5, job6 = created_jobs
        self.stdout.write('Created 6 jobs (4 in Tech Solutions, 2 in Global Corp) with stages and recruiter assignments')
        
        # 4. Create Candidates (talent pool) + linked Applications (decoupled join model for pipeline)
        # Status, stage, feedback now live on Application; Interview/ClientSubmission link to Application
        candidate_profiles = [
            ('Rahul Sharma', 'Python Backend Dev', 'TCS', '4.5 years', 'Bangalore', '15.2', '22.5', '60 days', 'Better opportunity'),
            ('Priya Patel', 'React Developer', 'Infosys', '3 years', 'Mumbai', '12.0', '18.0', '30 days', 'Role change'),
            ('Amit Kumar', 'DevOps Specialist', 'Wipro', '6 years', 'Hyderabad', '18.5', '25.0', '90 days', 'Career growth'),
            ('Sneha Reddy', 'Data Analyst', 'Accenture', '2.5 years', 'Chennai', '8.5', '14.0', '45 days', 'Better pay'),
            ('Vikram Singh', 'MERN Stack Dev', 'Cognizant', '5 years', 'Delhi', '16.0', '24.0', '30 days', 'Tech stack expansion'),
            ('Neha Gupta', 'HR Manager', 'HCL', '8 years', 'Pune', '22.0', '28.0', '60 days', 'Leadership role'),
            ('Rohan Malhotra', 'Senior Python Engineer', 'TechM', '7 years', 'Bangalore', '21.5', '30.0', '90 days', ''),
            ('Anjali Desai', 'Frontend Engineer', 'Capgemini', '4 years', 'Mumbai', '14.5', '20.0', '30 days', 'Work culture'),
            ('Karan Mehta', 'Cloud Architect', 'IBM', '9 years', 'Pune', '28.0', '35.0', '60 days', 'New challenges'),
            ('Meera Iyer', 'Business Analyst', 'Deloitte', '3 years', 'Hyderabad', '11.0', '16.5', '45 days', ''),
            ('Sanjay Rao', 'Full Stack Developer', 'Oracle', '5.5 years', 'Bangalore', '17.0', '23.5', '30 days', 'Better role'),
            ('Pooja Nair', 'Talent Acquisition', 'Google', '6 years', 'Mumbai', '19.0', '26.0', '60 days', ''),
            ('Arjun Khanna', 'DevOps Lead', 'Microsoft', '8 years', 'Hyderabad', '24.5', '32.0', '90 days', 'Senior position'),
            ('Divya Menon', 'UI/UX Developer', 'Adobe', '4 years', 'Bangalore', '13.8', '19.5', '45 days', 'Creative freedom'),
            ('Nikhil Verma', 'Data Scientist', 'Amazon', '5 years', 'Delhi', '19.5', '27.0', '60 days', 'AI/ML focus'),
        ]
        
        # Cycle through realistic statuses (now on Application)
        candidate_statuses = [
            CandidateStatus.SCREENING,
            CandidateStatus.INTERVIEW_SCHEDULED,
            CandidateStatus.SENT_TO_CLIENT,
            CandidateStatus.HIRED,
            CandidateStatus.REJECTED,
            CandidateStatus.ON_HOLD,
        ]
        status_stage_map = {
            CandidateStatus.SCREENING: "Screening",
            CandidateStatus.INTERVIEW_SCHEDULED: "HR Round",
            CandidateStatus.SENT_TO_CLIENT: "Technical",
            CandidateStatus.HIRED: "Hired",
            CandidateStatus.REJECTED: "Screening",
            CandidateStatus.ON_HOLD: "Screening",
        }
        
        jobs = created_jobs
        created_candidates = []
        created_applications = []
        
        for i, (name, profile, company, exp, loc, ctc, expctc, notice, reason) in enumerate(candidate_profiles):
            job = jobs[i % len(jobs)]
            recruiter = list(job.assigned_recruiters.all())[0] if job.assigned_recruiters.exists() else manager1
            
            status = candidate_statuses[i % len(candidate_statuses)]
            stage_name = status_stage_map.get(status, "Screening")
            stage = job.stages.filter(name=stage_name).first() or job.stages.order_by('order').first()
            
            # Some candidates have offer in hand or doc date
            offer = Decimal('18.5') if status == CandidateStatus.HIRED else None
            doc_date = date.today() - timedelta(days=random.randint(5, 60)) if i % 4 == 0 else None
            
            # Create pool Candidate (no job linkage)
            candidate = Candidate.objects.create(
                candidate_name=name,
                profile_name=profile,
                current_profile=profile,
                current_company=company,
                experience=exp,
                current_location=loc,
                preferred_location=random.choice(['Bangalore', 'Mumbai', 'Pune', 'Hyderabad', 'Remote']),
                education='B.Tech Computer Science',
                college='NIT / IIT',
                contact=f'+91-98{random.randint(1000000,9999999)}',
                email=f'{name.lower().replace(" ", ".")}@example.com',
                dob=date(1995, random.randint(1,12), random.randint(1,28)),
                doc=doc_date,
                current_ctc=Decimal(ctc),
                expected_ctc=Decimal(expctc),
                offer_in_hand=offer,
                notice_period=notice,
                reason_for_change=reason or 'Looking for new opportunities',
                resume_file_name=f'{name.lower().replace(" ", "_")}_resume.pdf',
                uploaded_by=recruiter,
                organization=job.organization
            )
            created_candidates.append(candidate)
            
            # Create Application (the join model carrying pipeline state)
            app = Application.objects.create(
                candidate=candidate,
                job=job,
                current_stage=stage,
                status=status,
                feedback='Strong technical skills, good communication.' if i % 3 != 0 else 'Average communication, needs improvement in DSA.',
                share_date=date.today() - timedelta(days=random.randint(0,30)),
                organization=job.organization
            )
            created_applications.append(app)
            
            # Add related objects based on status (now linked to Application, 1:1)
            if status == CandidateStatus.INTERVIEW_SCHEDULED:
                InterviewSchedule.objects.create(
                    application=app,
                    date=timezone.now().date() + timedelta(days=random.randint(1,5)),
                    time=time(random.randint(9,17), random.randint(0, 59)),
                    mode=random.choice(list(InterviewMode)),
                    interviewer_name=random.choice(['Priya Manager', 'Tech Lead Rajesh', 'Arjun Recruiter', 'Client Manager']),
                    notes='Focus on system design, past projects, and behavioral questions.',
                    organization=candidate.organization
                )
            elif status in [CandidateStatus.SENT_TO_CLIENT, CandidateStatus.HIRED, CandidateStatus.REJECTED]:
                sub_status = {
                    CandidateStatus.HIRED: SubmissionStatus.ACCEPTED,
                    CandidateStatus.REJECTED: SubmissionStatus.REJECTED,
                }.get(status, SubmissionStatus.REVIEWED)
                sent_by_user = manager1 if job.organization == org1 else manager2
                ClientSubmission.objects.create(
                    application=app,
                    sent_by=sent_by_user,
                    status=sub_status,
                    client_feedback='Excellent candidate with strong Python/Django background and good communication skills.' if status == CandidateStatus.HIRED else 'Candidate rejected due to salary expectations.' if status == CandidateStatus.REJECTED else 'Under review by hiring manager.',
                    client_rating=5 if status == CandidateStatus.HIRED else 2 if status == CandidateStatus.REJECTED else 4,
                    organization=candidate.organization
                )
                if status == CandidateStatus.HIRED:
                    app.feedback = 'Selected by client after final round. Offer extended at 28 LPA with 2 weeks joining.'
                    app.save()
                elif status == CandidateStatus.REJECTED:
                    app.feedback = 'Rejected by client - salary mismatch.'
                    app.save()
        
        self.stdout.write('Created 15 candidates (partitioned across organizations) + 15 Applications across all pipeline stages with matching stages, interviews & submissions')
        
        # 5. Create Audit Logs for key actions (with organization)
        audit_entries = [
            (admin1, AuditActionType.CREATED, 'Client', str(tcs.id), f'Created client {tcs.company_name} with CLI-{tcs.client_id}'),
            (manager1, AuditActionType.CREATED, 'Job', str(job1.id), f'Created job {job1.title} and auto-generated 6 stages'),
            (recruiter1, AuditActionType.CREATED, 'Candidate', str(created_candidates[0].id), f'Added new candidate {created_candidates[0].candidate_name}'),
            (manager1, AuditActionType.ASSIGNED, 'Job', str(job1.id), 'Assigned 2 recruiters to Senior Python Developer job'),
            (recruiter1, AuditActionType.UPDATED, 'Candidate', str(created_candidates[1].id), 'Updated status to INTERVIEW_SCHEDULED and created interview record'),
            (manager2, AuditActionType.SENT, 'Candidate', str(created_candidates[4].id), f'Submitted {created_candidates[4].candidate_name} to client for review'),
            (manager1, AuditActionType.CREATED, 'ClientSubmission', str(created_candidates[3].id), 'Client accepted candidate - moved to HIRED'),
            (admin1, AuditActionType.UPDATED, 'Client', str(wipro.id), 'Updated Wipro commercial terms and status to ON_HOLD'),
            (recruiter2, AuditActionType.DELETED, 'Candidate', 'DEMO-001', 'Soft deleted a duplicate candidate entry (demo)'),
        ]
        
        for user, action, entity, entity_id, details in audit_entries:
            AuditLog.objects.create(
                user=user,
                user_name=user.name,
                action=action,
                entity=entity,
                entity_id=entity_id,
                details=details,
                organization=user.organization
            )
        
        self.stdout.write('Created 9 sample audit logs')
        
        # 6. Create Notifications for different users/roles (with organization)
        notifications = [
            (manager1, 'New Candidate Added', f'{created_candidates[0].candidate_name} has been added to {job1.title}', NotificationType.SUCCESS, '/api/v1/candidates/'),
            (recruiter1, 'Interview Scheduled', f'Interview with {created_candidates[1].candidate_name} scheduled for tomorrow', NotificationType.INFO, '/api/v1/candidates/interviews/'),
            (manager2, 'Client Submission Update', f'{created_candidates[4].candidate_name} submitted to {wipro.company_name} - status updated', NotificationType.WARNING, f'/api/v1/jobs/{job5.id}/'),
            (admin1, 'Demo Data Seeded', 'Comprehensive demo data loaded successfully for 2 organizations. 7 users, 3 clients, 6 jobs, 15 candidates with full pipeline coverage.', NotificationType.SUCCESS, '/api/v1/dashboard/'),
            (recruiter3, 'New Job Assignment', f'You have been assigned to {job5.title}', NotificationType.INFO, '/api/v1/jobs/'),
            (manager1, 'Candidate Hired', f'Congratulations! {created_candidates[3].candidate_name} was hired by client', NotificationType.SUCCESS, '/api/v1/candidates/?status=hired'),
        ]
        
        for user, title, message, ntype, link in notifications:
            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                type=ntype,
                link=link,
                read=random.choice([True, False]),
                organization=user.organization
            )
        
        self.stdout.write('Created 6 sample notifications')
        
        self.stdout.write('\nSuccessfully seeded comprehensive multi-tenant demo data!')
        self.stdout.write('Login credentials:')
        self.stdout.write('  Tech Solutions:')
        self.stdout.write('    - Admin: admin@techsolutions.com / admin123')
        self.stdout.write('    - Manager: manager@techsolutions.com / manager123')
        self.stdout.write('    - Recruiter: recruiter@techsolutions.com / recruiter123')
        self.stdout.write('  Global Corp:')
        self.stdout.write('    - Admin: admin@globalcorp.com / admin123')
        self.stdout.write('    - Manager: manager@globalcorp.com / manager123')
        self.stdout.write('    - Recruiter: recruiter@globalcorp.com / recruiter123')
        self.stdout.write('\nThe database now contains realistic partitioned data across 2 organizations with full')
        self.stdout.write('tenant isolation, pipeline stages, audit trail, and notifications.')
        self.stdout.write('\nNew organizations can be registered via POST /api/v1/organizations/register/')
        self.stdout.write('\nRun "python manage.py runserver" to start the development server.')
