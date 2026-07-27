import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from accounts.models import Organization, User
from clients.models import Client
from jobs.models import Job, Stage
from candidates.models import (
    Candidate, Application, InterviewSchedule, ClientSubmission
)
from audit.models import AuditLog
from notifications.models import Notification

print('Organizations:', Organization.objects.count())
print('Users:', User.objects.count())
print('Clients:', Client.objects.count())
print('Jobs:', Job.objects.count())
print('Stages:', Stage.objects.count())
print('Candidates:', Candidate.objects.count())
print('Applications:', Application.objects.count())
print('InterviewSchedules:', InterviewSchedule.objects.count())
print('ClientSubmissions:', ClientSubmission.objects.count())
print('Audits:', AuditLog.objects.count())
print('Notifications:', Notification.objects.count())
for org in Organization.objects.all():
    print(f'\n{org.name}:')
    print('  Users:', User.objects.filter(organization=org).count())
    print('  Clients:', Client.objects.filter(organization=org).count())
    print('  Jobs:', Job.objects.filter(organization=org).count())
    print('  Stages:', Stage.objects.filter(organization=org).count())
    print('  Candidates:', Candidate.objects.filter(organization=org).count())
    print('  Applications:', Application.objects.filter(organization=org).count())
    print('  InterviewSchedules:', InterviewSchedule.objects.filter(organization=org).count())
    print('  ClientSubmissions:', ClientSubmission.objects.filter(organization=org).count())
    print('  Audits:', AuditLog.objects.filter(organization=org).count())
    print('  Notifications:', Notification.objects.filter(organization=org).count())
print('\nSeed data verification complete. (with Application join model)')
