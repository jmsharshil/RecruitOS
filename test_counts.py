import os
import django
from django.conf import settings

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from accounts.models import Organization, User
from clients.models import Client
from jobs.models import Job
from candidates.models import Candidate
from audit.models import AuditLog
from notifications.models import Notification

print('Organizations:', Organization.objects.count())
print('Users:', User.objects.count())
print('Clients:', Client.objects.count())
print('Jobs:', Job.objects.count())
print('Candidates:', Candidate.objects.count())
print('Audits:', AuditLog.objects.count())
print('Notifications:', Notification.objects.count())
for org in Organization.objects.all():
    print(f'\n{org.name}:')
    print('  Users:', User.objects.filter(organization=org).count())
    print('  Clients:', Client.objects.filter(organization=org).count())
    print('  Jobs:', Job.objects.filter(organization=org).count())
    print('  Candidates:', Candidate.objects.filter(organization=org).count())
    print('  Audits:', AuditLog.objects.filter(organization=org).count())
    print('  Notifications:', Notification.objects.filter(organization=org).count())
print('\nSeed data verification complete.')
