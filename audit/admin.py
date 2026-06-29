from django.contrib import admin
from audit.models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user_name', 'action', 'entity', 'entity_id']
    list_filter = ['action', 'entity']
    search_fields = ['user_name', 'details', 'entity_id']
    readonly_fields = ['timestamp']
