from django.contrib import admin
from candidates.models import Candidate, InterviewSchedule, ClientSubmission

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['candidate_name', 'current_company', 'job', 'status', 'current_stage', 'share_date']
    list_filter = ['status', 'share_date']
    search_fields = ['candidate_name', 'email', 'current_company', 'contact']

admin.site.register(InterviewSchedule)
admin.site.register(ClientSubmission)
