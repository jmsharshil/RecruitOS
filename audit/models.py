import uuid
from django.db import models
from accounts.models import User, Organization

class AuditActionType(models.TextChoices):
    CREATED  = 'created'
    UPDATED  = 'updated'
    DELETED  = 'deleted'
    SENT     = 'sent'
    ASSIGNED = 'assigned'
    READ     = 'read'
    LOGIN    = 'login'

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
    entity    = models.CharField(max_length=50, null=True, blank=True)     # 'Job', 'Candidate', 'Client', etc.
    entity_id = models.CharField(max_length=100, null=True, blank=True)
    details   = models.TextField(null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    
    # API tracking fields
    event       = models.CharField(max_length=255, null=True, blank=True)
    method      = models.CharField(max_length=10, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    path        = models.CharField(max_length=255, null=True, blank=True)
    user_role   = models.CharField(max_length=50, null=True, blank=True)
    user_email  = models.EmailField(null=True, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    user_agent  = models.TextField(null=True, blank=True)
    request_body = models.JSONField(null=True, blank=True)
    response_summary = models.JSONField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
