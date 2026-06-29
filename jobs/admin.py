from django.contrib import admin
from jobs.models import Job, Stage

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['title', 'hiring_for', 'client', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'hiring_for']
    search_fields = ['title', 'location']
    filter_horizontal = ['assigned_recruiters']

admin.site.register(Stage)
