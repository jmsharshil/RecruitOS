import uuid
from django.db import models
from accounts.models import User, Organization

class AuditActionType(models.TextChoices):
    CREATED  = 'created'
    UPDATED  = 'updated'
    DELETED  = 'deleted'
    SENT     = 'sent'
    ASSIGNED = 'assigned'

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='auditlog_related'
    )
    user      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    user_name = models.CharField(max_length=150)
    action    = models.CharField(max_length=20, choices=AuditActionType.choices)
    entity    = models.CharField(max_length=50)     # 'Job', 'Candidate', 'Client', etc.
    entity_id = models.CharField(max_length=100)
    details   = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
