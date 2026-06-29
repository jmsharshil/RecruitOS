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

class InterviewMode(models.TextChoices):
    ONLINE     = 'online'
    IN_PERSON  = 'in-person'
    TELEPHONIC = 'telephonic'

class SubmissionStatus(models.TextChoices):
    PENDING  = 'pending'
    REVIEWED = 'reviewed'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'

class Candidate(BaseModel):
    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job                = models.ForeignKey(Job, related_name='candidates', on_delete=models.CASCADE)
    profile_name       = models.CharField(max_length=200)
    candidate_name     = models.CharField(max_length=150)
    current_profile    = models.CharField(max_length=200)
    current_company    = models.CharField(max_length=200)
    experience         = models.CharField(max_length=50)
    current_location   = models.CharField(max_length=150)
    preferred_location = models.CharField(max_length=150, blank=True)
    education          = models.CharField(max_length=200, blank=True)
    college            = models.CharField(max_length=200, blank=True)
    contact            = models.CharField(max_length=20)
    email              = models.EmailField()
    dob                = models.DateField(null=True, blank=True)
    doc                = models.DateField(null=True, blank=True)
    current_ctc        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_ctc       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    offer_in_hand      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notice_period      = models.CharField(max_length=50)
    reason_for_change  = models.TextField(blank=True)
    share_date         = models.DateField(default=date.today)
    feedback           = models.TextField(blank=True)
    current_stage      = models.ForeignKey(Stage, null=True, blank=True, on_delete=models.SET_NULL, related_name='candidates')
    status             = models.CharField(max_length=30, choices=CandidateStatus.choices, default=CandidateStatus.SCREENING)
    resume             = models.FileField(upload_to='resumes/', null=True, blank=True)
    resume_file_name   = models.CharField(max_length=255, blank=True)
    is_deleted         = models.BooleanField(default=False)
    deleted_at         = models.DateTimeField(null=True, blank=True)
    created_by         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='added_candidates')

class InterviewSchedule(BaseModel):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate        = models.OneToOneField(Candidate, related_name='interview_schedule', on_delete=models.CASCADE)
    date             = models.DateField()
    time             = models.TimeField()
    mode             = models.CharField(max_length=20, choices=InterviewMode.choices)
    interviewer_name = models.CharField(max_length=150, blank=True)
    notes            = models.TextField(blank=True)

class ClientSubmission(BaseModel):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate       = models.OneToOneField(Candidate, related_name='client_submission', on_delete=models.CASCADE)
    sent_at         = models.DateTimeField(auto_now_add=True)
    sent_by         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status          = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.PENDING)
    client_feedback = models.TextField(blank=True)
    client_rating   = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-5
