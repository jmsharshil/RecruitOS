import uuid
from datetime import date
from django.db import models
from common.models import BaseModel
from accounts.models import User
from jobs.models import Job, Stage

class CandidateStatus(models.TextChoices):
    SCREENING           = 'screening'
    INTERVIEW_SCHEDULED = 'interview-scheduled'
    SENT_TO_CLIENT      = 'sent-to-client'
    HIRED               = 'hired'
    REJECTED            = 'rejected'
    ON_HOLD             = 'on-hold'
    INTERVIEW_ALIGN     = 'interview-align'
    SELECT              = 'select'
    OFFERED             = 'offered'
    JOINED              = 'joined'
    BACKOUT             = 'backout'

class InterviewMode(models.TextChoices):
    ONLINE     = 'online'
    IN_PERSON  = 'in-person'
    TELEPHONIC = 'telephonic'

class SubmissionStatus(models.TextChoices):
    PENDING  = 'pending'
    REVIEWED = 'reviewed'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'

class ManagerReviewStatus(models.TextChoices):
    PENDING  = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    RESUBMIT = 'resubmit'

class Candidate(BaseModel):
    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_name       = models.CharField(max_length=200)
    candidate_name     = models.CharField(max_length=150)
    current_profile    = models.CharField(max_length=200, blank=True, null=True)
    current_company    = models.CharField(max_length=200, blank=True, null=True)
    experience         = models.CharField(max_length=50, blank=True, null=True)
    current_location   = models.CharField(max_length=150, blank=True, null=True)
    education          = models.JSONField(default=list, blank=True)
    contact            = models.CharField(max_length=20, blank=True)
    email              = models.EmailField()
    resume             = models.FileField(upload_to='resumes/', null=True, blank=True)
    resume_file_name   = models.CharField(max_length=255, blank=True)
    uploaded_by        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='added_candidates')
    # Skills stored as JSON list for quick filtering
    skills             = models.JSONField(default=list, blank=True)
    # New AI parsed fields
    linkedin_url       = models.URLField(max_length=500, blank=True)
    portfolio_url      = models.URLField(max_length=500, blank=True)
    certifications     = models.JSONField(default=list, blank=True)
    experience_details = models.JSONField(default=list, blank=True)
    # General-purpose tags for internal categorization
    tags               = models.JSONField(default=list, blank=True)
    # Duplicate management
    is_duplicate       = models.BooleanField(default=False)
    duplicate_of       = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='duplicates'
    )
    
    # Salary & Availability fields on candidate level
    current_ctc        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_ctc       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notice_period      = models.CharField(max_length=50, blank=True)
    hike               = models.CharField(max_length=50, blank=True)
    
    # Additional common ATS fields
    preferred_location = models.CharField(max_length=150, blank=True, null=True)
    offer_in_hand      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reason_for_change  = models.TextField(blank=True, null=True)
    dob                = models.DateField(null=True, blank=True)


class Application(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(Candidate, related_name='applications', on_delete=models.CASCADE)
    job = models.ForeignKey(Job, related_name='applications', on_delete=models.CASCADE)
    current_stage = models.ForeignKey(
        Stage, null=True, blank=True, on_delete=models.SET_NULL, related_name='applications'
    )
    status = models.CharField(
        max_length=30, choices=CandidateStatus.choices, default="screening"
    )
    preferred_location = models.CharField(max_length=150, blank=True)
    current_ctc        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_ctc       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hike               = models.CharField(max_length=50, blank=True)
    offer_in_hand      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period      = models.CharField(max_length=50,blank=True)
    reason_for_change  = models.TextField(blank=True)
    dob                = models.DateField(null=True, blank=True)
    doc                = models.DateField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    share_date = models.DateField(default=date.today)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_applications'
    )
    manager_review_status = models.CharField(
        max_length=30, choices=ManagerReviewStatus.choices, default=ManagerReviewStatus.PENDING
    )
    manager_review_notes = models.TextField(blank=True)
    tracker_custom_fields = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('organization', 'candidate', 'job')


class InterviewSchedule(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, related_name='interview_schedule', on_delete=models.CASCADE
    )
    date = models.DateField()
    time = models.TimeField()
    mode = models.CharField(max_length=20, choices=InterviewMode.choices)
    interviewer_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)


class ClientSubmission(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.OneToOneField(
        Application, related_name='client_submission', on_delete=models.CASCADE
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_submissions')
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.PENDING)
    client_feedback = models.TextField(blank=True)
    client_rating = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-5


class ApplicationHistory(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='application_history_entries')
    action = models.CharField(max_length=50)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at']
