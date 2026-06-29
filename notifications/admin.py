from django.contrib import admin
from notifications.models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'type', 'read', 'created_at']
    list_filter = ['type', 'read']
    search_fields = ['title', 'message']
