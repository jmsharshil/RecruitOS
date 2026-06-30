from django.contrib import admin
from notifications.models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Enhanced notification admin with tenant and read status UX improvements."""
    list_display = ['user', 'title', 'type', 'read', 'organization', 'created_at']
    list_filter = ['type', 'read', 'organization']
    search_fields = ['title', 'message', 'user__email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
