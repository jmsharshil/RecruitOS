import uuid
from django.db import models
from django.conf import settings
from common.models import BaseModel
from accounts.models import User
from clients.models import Client

class HiringFor(models.TextChoices):
    SELF   = 'self'
    CLIENT = 'client'

class JobStatus(models.TextChoices):
    OPEN    = 'open'
    CLOSED  = 'closed'
    ON_HOLD = 'on-hold'

class JobTypes(models.TextChoices):
    PERMANENT   = 'permanent'
    CONTRACTUAL = 'contractual'

class JobModes(models.TextChoices):
    REMOTE = 'remote'
    HYBRID = 'hybrid'
    OFFICE = 'office'


class Priority(models.TextChoices):
    HIGH   = 'high'
    LOW    = 'low'
    MEDIUM = 'medium'

class Job(BaseModel):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title               = models.CharField(max_length=200)
    description         = models.TextField()
    code                = models.CharField(max_length=20, blank=True)  # auto-generated: JOB-000001 (unique per org)
    skills              = models.JSONField(default=list, blank=True)
    education           = models.CharField(max_length=200, blank=True)
    min_experience      = models.PositiveIntegerField(default=0)
    max_experience      = models.PositiveIntegerField(default=0)
    location            = models.CharField(max_length=150)
    openings            = models.PositiveIntegerField(default=1)
    priority            = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    budget              = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    job_mode            = models.CharField(max_length=20, choices=JobModes.choices, default=JobModes.OFFICE)
    job_type            = models.CharField(max_length=20, choices=JobTypes.choices, default=JobTypes.PERMANENT)
    hiring_for          = models.CharField(max_length=10, choices=HiringFor.choices, default=HiringFor.SELF)
    client              = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='jobs')
    status              = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.OPEN)
    assigned_recruiters = models.ManyToManyField(User, related_name='assigned_jobs', blank=True, limit_choices_to={'role': 'recruiter'})
    target_closing_date = models.DateField(null=True, blank=True)
    notice_period_preference = models.CharField(max_length=50, blank=True)
    skill_criteria      = models.DecimalField(max_digits=5, decimal_places=2, default=70.0)
    created_by          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_jobs')

    class Meta:
        unique_together = ('organization', 'code')

    def save(self, *args, **kwargs):
        if not self.code and getattr(self, 'organization', None) is not None:
            # Robust organization-scoped code generation (JOB-000001 format)
            prefix = "JOB-"
            last = Job.objects.filter(
                organization=self.organization,
                code__startswith=prefix
            ).order_by('-code').first()
            if last and last.code and last.code.startswith(prefix):
                try:
                    last_num = int(last.code[len(prefix):])
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1
            self.code = f"{prefix}{next_num:06d}"
        super().save(*args, **kwargs)

class Stage(BaseModel):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job        = models.ForeignKey(Job, related_name='stages', on_delete=models.CASCADE)
    name       = models.CharField(max_length=100)
    order      = models.PositiveIntegerField(default=0)
    color      = models.CharField(max_length=20, default='indigo')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_stages')

    class Meta:
        ordering = ['order']

DEFAULT_STAGES = [
    {"name": "Screening",    "order": 1, "color": "slate"},
    {"name": "HR Round",     "order": 2, "color": "blue"},
    {"name": "Technical",    "order": 3, "color": "indigo"},
    {"name": "Client Round", "order": 4, "color": "sky"},
    {"name": "Offer",        "order": 5, "color": "amber"},
    {"name": "Hired",        "order": 6, "color": "green"},
]
