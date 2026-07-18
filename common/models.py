from django.db import models
from accounts.models import Organization

class BaseModel(models.Model):
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='%(class)s_related'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
