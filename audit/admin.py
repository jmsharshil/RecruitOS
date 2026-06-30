from django.contrib import admin
from audit.models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only audit trail with organization filter for compliance UX."""
    list_display = ['timestamp', 'user_name', 'action', 'entity', 'entity_id', 'organization']
    list_filter = ['action', 'entity', 'organization']
    search_fields = ['user_name', 'details', 'entity_id']
    readonly_fields = ['timestamp', 'created_at']
    ordering = ['-timestamp']
