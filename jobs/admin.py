from django.contrib import admin
from jobs.models import Job, Stage

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Enhanced Job admin with organization filter and recruiter display."""
    list_display = ['title', 'hiring_for', 'client', 'status', 'organization', 'created_by', 'created_at']
    list_filter = ['status', 'hiring_for', 'organization']
    search_fields = ['title', 'location', 'description']
    filter_horizontal = ['assigned_recruiters']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    """Pipeline stage admin with ordering and job-specific view."""
    list_display = ['name', 'job', 'order', 'color', 'organization']
    list_filter = ['job', 'organization']
    search_fields = ['name', 'job__title']
    ordering = ['job', 'order']
    readonly_fields = ['created_at', 'updated_at']
