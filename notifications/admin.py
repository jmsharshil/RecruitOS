from django.contrib import admin
from notifications.models import Notification, EmailLog

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Enhanced notification admin with tenant and read status UX improvements."""
    list_display = ['user', 'title', 'type', 'read', 'organization', 'created_at']
    list_filter = ['type', 'read', 'organization']
    search_fields = ['title', 'message', 'user__email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['subject', 'recipient_email', 'sender', 'status', 'sent_at', 'organization']
    list_filter = ['status', 'email_type', 'organization']
    search_fields = ['subject', 'recipient_email', 'sender__email', 'candidate_name']
    readonly_fields = ['sent_at']
    ordering = ['-sent_at']