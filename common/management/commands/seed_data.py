from django.core.management.base import BaseCommand
from accounts.models import User, UserRole
from clients.models import Client, POC, POCType, ClientStatus, ClientDocument
from jobs.models import Job, HiringFor, JobStatus
from candidates.models import Candidate, CandidateStatus, InterviewSchedule, InterviewMode, ClientSubmission, SubmissionStatus
from audit.models import AuditLog, AuditActionType
from notifications.models import Notification, NotificationType
from django.utils import timezone
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with mock data for HRMS'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')
        
        # 1. Users
        admin = User.objects.create_superuser(email='admin@recruitsmart.com', name='Raj Admin', role=UserRole.ADMIN, password='admin123')
        manager1 = User.objects.create_user(email='manager@recruitsmart.com', name='Priya Manager', role=UserRole.MANAGER, password='manager123', created_by=admin)
        manager2 = User.objects.create_user(email='manager2@recruitsmart.com', name='Vikram Manager', role=UserRole.MANAGER, password='manager123', created_by=admin)
        recruiter1 = User.objects.create_user(email='recruiter@recruitsmart.com', name='Arjun Recruiter', role=UserRole.RECRUITER, password='recruiter123', created_by=manager1)
        recruiter2 = User.objects.create_user(email='recruiter2@recruitsmart.com', name='Meera Recruiter', role=UserRole.RECRUITER, password='recruiter123', created_by=manager1)
        recruiter3 = User.objects.create_user(email='recruiter3@recruitsmart.com', name='Karan Recruiter', role=UserRole.RECRUITER, password='recruiter123', created_by=manager2)
        
        self.stdout.write('Created users')
        
        # 2. Clients
        tcs = Client.objects.create(company_name='TCS', client_name='Ravi Kumar', email='ravi@tcs.com', contact='+91 9000000001', industry='IT Services', city='Mumbai', status=ClientStatus.ACTIVE, created_by=admin)
        infosys = Client.objects.create(company_name='Infosys', client_name='Sunita Verma', email='sunita@infosys.com', contact='+91 9000000002', industry='IT Services', city='Pune', status=ClientStatus.ACTIVE, created_by=manager1)
        wipro = Client.objects.create(company_name='Wipro', client_name='Amit Singh', email='amit@wipro.com', contact='+91 9000000003', industry='IT Services', city='Bengaluru', status=ClientStatus.ON_HOLD, created_by=manager2)
        
        for client in [tcs, infosys, wipro]:
            POC.objects.create(client=client, poc_type=POCType.HIRING, name=f'Hiring POC 1 {client.company_name}', email=f'hiring1@{client.company_name.lower()}.com', designation='HR', contact='12345')
            POC.objects.create(client=client, poc_type=POCType.HIRING, name=f'Hiring POC 2 {client.company_name}', email=f'hiring2@{client.company_name.lower()}.com', designation='TA', contact='12346')
            POC.objects.create(client=client, poc_type=POCType.PAYMENT, name=f'Payment POC {client.company_name}', email=f'finance@{client.company_name.lower()}.com', designation='Finance', contact='12347')
            ClientDocument.objects.create(client=client, file_name='dummy_agreement.pdf')

        self.stdout.write('Created clients')

        # 3. Jobs
        job1 = Job.objects.create(title='Senior Python Developer', client=tcs, status=JobStatus.OPEN, hiring_for=HiringFor.CLIENT, created_by=manager1, experience='3-6 years', location='Bengaluru', skills=['Python', 'Django'])
        job1.assigned_recruiters.set([recruiter1, recruiter2])
        
        job2 = Job.objects.create(title='React Frontend Engineer', client=tcs, status=JobStatus.OPEN, hiring_for=HiringFor.CLIENT, created_by=manager1, experience='2-4 years', location='Mumbai', skills=['React', 'JS'])
        job2.assigned_recruiters.set([recruiter1])
        
        job3 = Job.objects.create(title='DevOps Engineer', client=infosys, status=JobStatus.OPEN, hiring_for=HiringFor.CLIENT, created_by=manager1, experience='4-8 years', location='Pune', skills=['AWS', 'Docker'])
        job3.assigned_recruiters.set([recruiter2, recruiter3])
        
        job4 = Job.objects.create(title='Data Analyst', client=infosys, status=JobStatus.ON_HOLD, hiring_for=HiringFor.CLIENT, created_by=manager1, experience='1-3 years', location='Pune', skills=['SQL', 'Excel'])
        job4.assigned_recruiters.set([recruiter3])
        
        job5 = Job.objects.create(title='Full Stack Developer', client=wipro, status=JobStatus.OPEN, hiring_for=HiringFor.CLIENT, created_by=manager2, experience='5+ years', location='Bengaluru', skills=['MERN'])
        job5.assigned_recruiters.set([recruiter1])
        
        job6 = Job.objects.create(title='HR Business Partner', status=JobStatus.OPEN, hiring_for=HiringFor.SELF, created_by=manager2, experience='8+ years', location='Mumbai', skills=['HR', 'Recruitment'])
        job6.assigned_recruiters.set([recruiter2])

        self.stdout.write('Created jobs')
        
        # 4. Candidates
        jobs = [job1, job2, job3, job4, job5, job6]
        c_count = 0
        for i in range(15):
            job = jobs[i % len(jobs)]
            c = Candidate.objects.create(
                job=job,
                candidate_name=f'Candidate {i+1}',
                profile_name=f'Candidate {i+1}',
                current_company='Accenture' if i % 2 == 0 else 'Cognizant',
                experience='3 years',
                current_location='Mumbai',
                email=f'candidate{i+1}@example.com',
                contact='+91 9999999999',
                created_by=job.assigned_recruiters.first(),
                current_stage=job.stages.first(),
                status=CandidateStatus.SCREENING
            )
            c_count += 1
            if i < 3: # interviews
                InterviewSchedule.objects.create(candidate=c, date=timezone.now().date() + datetime.timedelta(days=1), time=datetime.time(10, 0), mode=InterviewMode.ONLINE)
                c.status = CandidateStatus.INTERVIEW_SCHEDULED
            elif i < 6: # submissions
                ClientSubmission.objects.create(candidate=c, sent_by=manager1, status=SubmissionStatus.PENDING)
                c.status = CandidateStatus.SENT_TO_CLIENT
            elif i < 8: # hired
                c.status = CandidateStatus.HIRED
            elif i < 10: # rejected
                c.status = CandidateStatus.REJECTED
            c.save()

        self.stdout.write(f'Created {c_count} candidates')
        
        # 5. Audit logs
        AuditLog.objects.create(user=admin, user_name='Raj Admin', action=AuditActionType.CREATED, entity='Job', entity_id=str(job1.id), details='Created job via seed')
        AuditLog.objects.create(user=manager1, user_name='Priya Manager', action=AuditActionType.SENT, entity='Candidate', entity_id='some-id', details='Sent to client')
        
        # 6. Notifications
        Notification.objects.create(user=manager1, title='System update', message='Seed completed', type=NotificationType.SUCCESS)
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded database!'))
