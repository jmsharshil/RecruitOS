import uuid
from django.db import models
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

class Job(BaseModel):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title               = models.CharField(max_length=200)
    description         = models.TextField()
    skills              = models.JSONField(default=list)          # ["Python", "Django", ...]
    experience          = models.CharField(max_length=50)         # "2-4 years"
    location            = models.CharField(max_length=150)
    hiring_for          = models.CharField(max_length=10, choices=HiringFor.choices, default=HiringFor.SELF)
    client              = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name='jobs')
    status              = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.OPEN)
    assigned_recruiters = models.ManyToManyField(User, related_name='assigned_jobs', blank=True, limit_choices_to={'role': 'recruiter'})
    resume_upload_link  = models.CharField(max_length=500, blank=True)
    created_by          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_jobs')

    def save(self, *args, **kwargs):
        if not self.resume_upload_link:
            # We use a dummy link for now, in a real app this would use the frontend URL from settings
            self.resume_upload_link = f"https://frontend.app/upload/{self.id}"
        super().save(*args, **kwargs)

class Stage(BaseModel):
    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job   = models.ForeignKey(Job, related_name='stages', on_delete=models.CASCADE)
    name  = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default='indigo')

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
