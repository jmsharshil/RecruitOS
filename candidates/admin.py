from django.contrib import admin
from candidates.models import Candidate, InterviewSchedule, ClientSubmission

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    """Enhanced Candidate admin with full pipeline visibility and tenant scoping."""
    list_display = ['candidate_name', 'current_company', 'job', 'status', 'current_stage', 'organization', 'share_date']
    list_filter = ['status', 'current_stage', 'organization', 'share_date']
    search_fields = ['candidate_name', 'email', 'current_company', 'contact']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InterviewSchedule)
class InterviewScheduleAdmin(admin.ModelAdmin):
    """Interview scheduling admin with candidate and date filters."""
    list_display = ['candidate', 'date', 'time', 'mode', 'interviewer_name', 'organization']
    list_filter = ['mode', 'date', 'organization']
    search_fields = ['candidate__candidate_name', 'interviewer_name', 'notes']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ClientSubmission)
class ClientSubmissionAdmin(admin.ModelAdmin):
    """Client submission admin for tracking feedback and status."""
    list_display = ['candidate', 'status', 'sent_at', 'sent_by', 'client_rating', 'organization']
    list_filter = ['status', 'organization', 'sent_at']
    search_fields = ['candidate__candidate_name', 'client_feedback']
    readonly_fields = ['sent_at', 'created_at', 'updated_at']
