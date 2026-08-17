from rest_framework import serializers
from candidates.models import Candidate, Application, InterviewSchedule, ClientSubmission, ManagerReviewStatus, ApplicationHistory
from jobs.models import Job, Stage
from jobs.serializers import StageBriefSerializer, JobBriefSerializer
from accounts.serializers import UserBriefSerializer
from common.serializers import DateParserField, DateParserDateTimeField


class CandidateBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            'id', 'candidate_name', 'email', 'contact', 'current_profile',
            'current_company', 'experience', 'current_location', 'skills',
            'education', 'linkedin_url', 'portfolio_url', 'certifications', 'tags',
            'resume_file_name', 'is_duplicate', 'duplicate_of',
        ]


class InterviewScheduleSerializer(serializers.ModelSerializer):
    date       = DateParserField(required=False, allow_null=True)
    created_at = DateParserDateTimeField(read_only=True)
    updated_at = DateParserDateTimeField(read_only=True)
    deleted_at = DateParserDateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ['id', 'application', 'organization', 'is_deleted', 'manager_approval_status', 'attendance_status']


class ClientSubmissionSerializer(serializers.ModelSerializer):
    sent_by = UserBriefSerializer(read_only=True)
    sent_at     = DateParserDateTimeField(required=False, allow_null=True)
    created_at  = DateParserDateTimeField(read_only=True)
    updated_at  = DateParserDateTimeField(read_only=True)
    deleted_at  = DateParserDateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = ClientSubmission
        fields = '__all__'
        read_only_fields = ['id', 'application', 'organization', 'is_deleted']


# ---------------------------------------------------------------------------
# Application serializers
# ---------------------------------------------------------------------------

class ApplicationHistorySerializer(serializers.ModelSerializer):
    user_details = UserBriefSerializer(source='user', read_only=True)
    created_at   = DateParserDateTimeField(read_only=True)

    class Meta:
        model = ApplicationHistory
        fields = ['id', 'user_details', 'action', 'notes', 'created_at']

class ApplicationListSerializer(serializers.ModelSerializer):
    """Flat list — candidate name, job title, status, stage. No deep nesting.
    Updated to include fields moved from Candidate model (ctc, notice_period, etc).
    """
    candidate_name = serializers.CharField(source='candidate.candidate_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)
    candidate_contact = serializers.CharField(source='candidate.contact', read_only=True)
    candidate_experience = serializers.CharField(source='candidate.experience', read_only=True)
    candidate_current_profile = serializers.CharField(source='candidate.current_profile', read_only=True)
    candidate_current_company = serializers.CharField(source='candidate.current_company', read_only=True)
    candidate_current_location = serializers.CharField(source='candidate.current_location', read_only=True)
    
    candidate_skills = serializers.JSONField(source='candidate.skills', read_only=True)
    candidate_education = serializers.JSONField(source='candidate.education', read_only=True)
    
    current_ctc = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    expected_ctc = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    notice_period = serializers.CharField(read_only=True)
    hike = serializers.CharField(read_only=True)
    preferred_location = serializers.CharField(read_only=True)
    offer_in_hand = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    reason_for_change = serializers.CharField(read_only=True)
    dob = serializers.DateField(read_only=True)
    
    job_title      = serializers.CharField(source='job.title', read_only=True)
    stage_name     = serializers.SerializerMethodField()
    share_date     = DateParserField(required=False, allow_null=True)
    created_at     = DateParserDateTimeField(read_only=True)
    # Write fields
    job_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Job.objects.all(), source='job'
    )
    candidate_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Candidate.objects.all(), source='candidate'
    )
    current_stage_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Stage.objects.all(), source='current_stage',
        required=False, allow_null=True
    )

    submitted_by   = serializers.SerializerMethodField()
    candidate_cv   = serializers.SerializerMethodField()
    interview_schedule = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'candidate_name', 'candidate_email', 'candidate_contact',
            'candidate_experience', 'candidate_current_profile',
            'candidate_current_company', 'candidate_current_location',
            'candidate_skills', 'candidate_education',
            'job_title', 'status', 'stage_name', 'share_date', 'created_at',
            'current_ctc', 'expected_ctc', 'notice_period', 'hike',
            'preferred_location', 'offer_in_hand', 'reason_for_change', 'dob',
            'submitted_by', 'candidate_cv', 'interview_schedule',
            'manager_review_status', 'manager_review_notes',
            # write-only
            'job_id', 'candidate_id', 'current_stage_id',
        ]
        read_only_fields = ['id', 'organization', 'manager_review_status', 'manager_review_notes']

    def get_stage_name(self, obj):
        return obj.current_stage.name if obj.current_stage else None

    def get_interview_schedule(self, obj):
        try:
            return InterviewScheduleSerializer(obj.interview_schedule).data
        except InterviewSchedule.DoesNotExist:
            return None

    def get_candidate_cv(self, obj):
        request = self.context.get('request')
        if obj.candidate.resume:
            return request.build_absolute_uri(obj.candidate.resume.url) if request else obj.candidate.resume.url
        return None

    def get_submitted_by(self, obj):
        user = obj.created_by or obj.candidate.uploaded_by
        if user:
            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role
            }
        return None

    def validate(self, attrs):
        candidate = attrs.get('candidate')
        job = attrs.get('job')
        request = self.context.get('request')
        if not request or not request.user:
            return attrs
        organization = request.user.organization
        
        if candidate and job:
            qs = Application.objects.filter(organization=organization, candidate=candidate, job=job, is_deleted=False)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["This candidate is already linked to this job requisition."]
                })
        return attrs


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Full nested detail — candidate, job, stage, interview, submission.
    Updated for model changes (dob, doc, ctc fields now here).
    """
    current_stage      = StageBriefSerializer(read_only=True)
    job                = JobBriefSerializer(read_only=True)
    candidate          = CandidateBriefSerializer(read_only=True)
    interview_schedule = serializers.SerializerMethodField()
    client_submission  = serializers.SerializerMethodField()
    submitted_by       = serializers.SerializerMethodField()
    candidate_cv       = serializers.SerializerMethodField()
    past_jobs          = serializers.SerializerMethodField()
    history            = ApplicationHistorySerializer(many=True, read_only=True)
    share_date         = DateParserField(required=False, allow_null=True)
    dob                = DateParserField(required=False, allow_null=True)
    doc                = DateParserField(required=False, allow_null=True)
    created_at         = DateParserDateTimeField(read_only=True)
    updated_at         = DateParserDateTimeField(read_only=True)
    deleted_at         = DateParserDateTimeField(read_only=True, allow_null=True)
    job_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Job.objects.all(), source='job'
    )
    candidate_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Candidate.objects.all(), source='candidate'
    )
    current_stage_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Stage.objects.all(), source='current_stage',
        required=False, allow_null=True
    )
    notes = serializers.CharField(source='feedback', required=False, allow_blank=True)

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'is_deleted', 'manager_review_status', 'manager_review_notes']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.pop('feedback', None)
        return ret

    def get_interview_schedule(self, obj):
        try:
            return InterviewScheduleSerializer(obj.interview_schedule).data
        except InterviewSchedule.DoesNotExist:
            return None

    def get_client_submission(self, obj):
        try:
            return ClientSubmissionSerializer(obj.client_submission).data
        except ClientSubmission.DoesNotExist:
            return None

    def get_candidate_cv(self, obj):
        request = self.context.get('request')
        if obj.candidate.resume:
            return request.build_absolute_uri(obj.candidate.resume.url) if request else obj.candidate.resume.url
        return None

    def get_submitted_by(self, obj):
        user = obj.created_by or obj.candidate.uploaded_by
        if user:
            return {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role
            }
        return None

    def validate(self, attrs):
        candidate = attrs.get('candidate')
        job = attrs.get('job')
        request = self.context.get('request')
        if not request or not request.user:
            return attrs
        organization = request.user.organization
        
        if candidate and job:
            qs = Application.objects.filter(organization=organization, candidate=candidate, job=job, is_deleted=False)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["This candidate is already linked to this job requisition."]
                })
        
        required_fields = {
            'current_ctc': 'Current CTC',
            'expected_ctc': 'Expected CTC',
            'hike': 'Hike',
            'notice_period': 'Notice Period',
            'offer_in_hand': 'Offer in Hand',
            'preferred_location': 'Pref. Location',
            'reason_for_change': 'Reason for Change',
            'dob': 'Date of Birth'
        }
        
        errors = {}
        for field, label in required_fields.items():
            val = attrs.get(field)
            if val is None:
                if self.instance:
                    val = getattr(self.instance, field, None)
                elif candidate:
                    val = getattr(candidate, field, None)
                    
            if val in [None, '', 'Not specified', 'Not provided', 0, 0.0, '0', '0.0']:
                errors[field] = f"{label} is required."
                
        if errors:
            raise serializers.ValidationError(errors)
            
        return attrs

    def get_past_jobs(self, obj):
        from candidates.models import Application
        apps = Application.objects.filter(
            candidate=obj.candidate,
            organization=obj.organization,
            is_deleted=False
        ).select_related(
            'job', 'job__client', 'current_stage', 'organization',
            'candidate', 'created_by', 'candidate__uploaded_by', 'job__hiring_manager', 'job__created_by'
        )
        
        past = []
        for app in apps:
            company = app.job.client.company_name if app.job.client else (app.organization.name if app.organization else "Internal")
            recruiter = app.created_by or app.candidate.uploaded_by
            recruiter_name = recruiter.name if recruiter else None
            job_manager = app.job.hiring_manager or app.job.created_by
            manager_name = job_manager.name if job_manager else None
            
            past.append({
                "candidate_name": app.candidate.candidate_name,
                "email": app.candidate.email,
                "job_id": app.job.id,
                "job_title": app.job.title,
                "company_name": company,
                "status": app.status,
                "stage": app.current_stage.name if app.current_stage else None,
                "manager_review_status": app.manager_review_status,
                "manager_review_notes": app.manager_review_notes,
                "recruiter_name": recruiter_name,
                "manager_name": manager_name,
                "created_at": app.created_at
            })
        return past

# ---------------------------------------------------------------------------
# Candidate serializers
# ---------------------------------------------------------------------------

class CandidateListSerializer(serializers.ModelSerializer):
    """Flat list — essential fields only, no nested applications.
    Note: CTC, notice_period, reason_for_change moved to per-job Application model.
    """
    uploaded_by_name    = serializers.SerializerMethodField()
    # applications_count  = serializers.SerializerMethodField()
    # duplicate_of_name   = serializers.SerializerMethodField()
    created_at          = DateParserDateTimeField(read_only=True)

    class Meta:
        model = Candidate
        fields = [
            'id', 'candidate_name', 'email', 'contact',
            'current_profile', 'current_company', 'experience',
            'current_location', 'is_duplicate',
            'uploaded_by_name', 'created_at',
            # 'resume_file_name', 'duplicate_of_name', 'applications_count', 'skills',
        ]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.name if obj.uploaded_by else None

    # def get_applications_count(self, obj):
    #     return obj.applications.filter(is_deleted=False).count()
    #
    # def get_duplicate_of_name(self, obj):
    #     return obj.duplicate_of.candidate_name if obj.duplicate_of_id else None


class CandidateDetailSerializer(serializers.ModelSerializer):
    """Full detail — all fields + nested applications + uploader info.
    Note: Fields like dob, doc, ctc, notice_period, reason_for_change moved to Application.
    """
    applications         = ApplicationListSerializer(many=True, read_only=True)
    past_jobs            = serializers.SerializerMethodField()
    uploaded_by          = UserBriefSerializer(read_only=True)
    duplicate_of_detail  = CandidateBriefSerializer(source='duplicate_of', read_only=True)
    created_at           = DateParserDateTimeField(read_only=True)
    updated_at           = DateParserDateTimeField(read_only=True)
    deleted_at           = DateParserDateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = Candidate
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'is_deleted', 'deleted_at',
            'organization', 'uploaded_by',
        ]

    def to_internal_value(self, data):
        # Handle empty strings for Decimal fields sent by the frontend
        mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
        for field in ['current_ctc', 'expected_ctc']:
            if field in mutable_data and mutable_data[field] in ["", None]:
                mutable_data[field] = 0
        if 'offer_in_hand' in mutable_data and mutable_data['offer_in_hand'] in ["", None]:
            mutable_data['offer_in_hand'] = None
            
        return super().to_internal_value(mutable_data)

    def update(self, instance, validated_data):
        # Automatically keep profile_name synced with candidate_name if it's updated
        if 'candidate_name' in validated_data and 'profile_name' not in validated_data:
            validated_data['profile_name'] = validated_data['candidate_name']
        return super().update(instance, validated_data)

    def get_past_jobs(self, obj):
        from candidates.models import Application
        apps = Application.objects.filter(
            candidate=obj,
            organization=obj.organization,
            is_deleted=False
        ).select_related(
            'job', 'job__client', 'current_stage', 'organization', 
            'created_by', 'candidate__uploaded_by', 'job__hiring_manager', 'job__created_by'
        )
        
        past = []
        for app in apps:
            company = app.job.client.company_name if app.job.client else (app.organization.name if app.organization else "Internal")
            recruiter = app.created_by or app.candidate.uploaded_by
            recruiter_name = recruiter.name if recruiter else None
            job_manager = app.job.hiring_manager or app.job.created_by
            manager_name = job_manager.name if job_manager else None

            past.append({
                "application_id": app.id,
                "job_id": app.job.id,
                "job_title": app.job.title,
                "company_name": company,
                "job_location": app.job.location,
                "job_mode": app.job.job_mode,
                "stage": app.current_stage.name if app.current_stage else None,
                "status": app.status,
                "manager_review_status": app.manager_review_status,
                "manager_review_notes": app.manager_review_notes,
                "created_at": app.created_at,
                "updated_at": app.updated_at,
                "recruiter_name": recruiter_name,
                "manager_name": manager_name
            })
        return past