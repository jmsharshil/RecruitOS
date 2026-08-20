import uuid
from django.db import models
from common.models import BaseModel
from accounts.models import User, Organization

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
