from django.contrib import admin
from candidates.models import (
    Candidate, Application, InterviewSchedule, ClientSubmission
)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    """Enhanced Candidate admin with full pipeline visibility and tenant scoping."""
    list_display = [
        'candidate_name', 'current_company', 'get_job', 'get_status',
        'get_current_stage', 'organization', 'get_share_date'
    ]
    list_filter = ['organization', 'applications__status', 'applications__current_stage']
    search_fields = ['candidate_name', 'email', 'current_company', 'contact']
    readonly_fields = ['created_at', 'updated_at']

    def get_job(self, obj):
        """Get job title from the first application."""
        application = obj.applications.first()
        return application.job.title if application and application.job else '-'

    get_job.short_description = 'Job'
    get_job.admin_order_field = 'applications__job__title'

    def get_status(self, obj):
        """Get status from the first application."""
        application = obj.applications.first()
        return application.get_status_display() if application else '-'

    get_status.short_description = 'Status'
    get_status.admin_order_field = 'applications__status'

    def get_current_stage(self, obj):
        """Get current stage from the first application."""
        application = obj.applications.first()
        if application and application.current_stage:
            return application.current_stage.name
        return '-'

    get_current_stage.short_description = 'Current Stage'
    get_current_stage.admin_order_field = 'applications__current_stage__name'

    def get_share_date(self, obj):
        """Get share date from the first application."""
        application = obj.applications.first()
        return application.share_date if application else '-'

    get_share_date.short_description = 'Share Date'
    get_share_date.admin_order_field = 'applications__share_date'


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Application admin to manage candidate-job relationships and pipeline stages."""
    list_display = ['candidate', 'job', 'status', 'current_stage', 'share_date', 'organization']
    list_filter = ['status', 'current_stage', 'organization', 'share_date']
    search_fields = ['candidate__candidate_name', 'job__title', 'feedback']
    readonly_fields = ['created_at', 'updated_at']

    def candidate(self, obj):
        return obj.candidate.candidate_name if obj.candidate else '-'

    candidate.short_description = 'Candidate'
    candidate.admin_order_field = 'candidate__candidate_name'

    def job(self, obj):
        return obj.job.title if obj.job else '-'

    job.short_description = 'Job'
    job.admin_order_field = 'job__title'


@admin.register(InterviewSchedule)
class InterviewScheduleAdmin(admin.ModelAdmin):
    """Interview scheduling admin with candidate and date filters."""
    list_display = ['get_candidate', 'date', 'time', 'mode', 'interviewer_name', 'organization']
    list_filter = ['mode', 'date', 'organization']
    search_fields = ['application__candidate__candidate_name', 'interviewer_name', 'notes']
    readonly_fields = ['created_at', 'updated_at']

    def get_candidate(self, obj):
        """Get candidate name through application relationship."""
        if obj.application and obj.application.candidate:
            return obj.application.candidate.candidate_name
        return '-'

    get_candidate.short_description = 'Candidate'
    get_candidate.admin_order_field = 'application__candidate__candidate_name'


@admin.register(ClientSubmission)
class ClientSubmissionAdmin(admin.ModelAdmin):
    """Client submission admin for tracking feedback and status."""
    list_display = ['get_candidate', 'status', 'sent_at', 'sent_by', 'client_rating', 'organization']
    list_filter = ['status', 'organization', 'sent_at']
    search_fields = ['application__candidate__candidate_name', 'client_feedback']
    readonly_fields = ['sent_at', 'created_at', 'updated_at']

    def get_candidate(self, obj):
        """Get candidate name through application relationship."""
        if obj.application and obj.application.candidate:
            return obj.application.candidate.candidate_name
        return '-'

    get_candidate.short_description = 'Candidate'
    get_candidate.admin_order_field = 'application__candidate__candidate_name'
