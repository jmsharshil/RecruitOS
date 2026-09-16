import uuid
from django.db import models
from common.models import BaseModel
from accounts.models import User, Organization
from candidates.models import Candidate

class NotificationType(models.TextChoices):
    INFO    = 'info'
    SUCCESS = 'success'
    WARNING = 'warning'
    ERROR   = 'error'

class Notification(BaseModel):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, related_name='notifications', on_delete=models.CASCADE)
    from_user  = models.ForeignKey(User, related_name='sent_notifications', on_delete=models.SET_NULL, null=True, blank=True)
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    type       = models.CharField(max_length=10, choices=NotificationType.choices, default=NotificationType.INFO)
    name       = models.CharField(max_length=255, blank=True, null=True)
    event      = models.CharField(max_length=255, blank=True, null=True)
    process    = models.CharField(max_length=255, blank=True, null=True)
    read       = models.BooleanField(default=False)
    link       = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class EmailLog(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_emails')
    recipient_email = models.EmailField()
    cc_emails = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=255)
    body_text = models.TextField(blank=True, null=True)
    body_html = models.TextField()
    event = models.CharField(max_length=100, blank=True, null=True)
    email_type = models.CharField(max_length=50, blank=True, null=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.SET_NULL, null=True, blank=True)
    candidate_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default='sent')
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']
