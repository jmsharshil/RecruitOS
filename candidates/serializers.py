from rest_framework import serializers
from candidates.models import Candidate, Application, InterviewSchedule, ClientSubmission
from jobs.models import Job, Stage
from jobs.serializers import StageBriefSerializer, JobBriefSerializer
from accounts.serializers import UserBriefSerializer
from common.serializers import DateParserField, DateParserDateTimeField


class CandidateBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            'id', 'candidate_name', 'email', 'contact', 'current_profile',
            'current_company', 'experience', 'resume_file_name',
            'is_duplicate', 'duplicate_of',
        ]


class InterviewScheduleSerializer(serializers.ModelSerializer):
    date       = DateParserField(required=False, allow_null=True)
    created_at = DateParserDateTimeField(read_only=True)
    updated_at = DateParserDateTimeField(read_only=True)
    deleted_at = DateParserDateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ['id', 'application', 'organization', 'is_deleted']


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

class ApplicationListSerializer(serializers.ModelSerializer):
    """Flat list — candidate name, job title, status, stage. No deep nesting."""
    candidate_name = serializers.CharField(source='candidate.candidate_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)
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

    class Meta:
        model = Application
        fields = [
            'id', 'candidate_name', 'candidate_email', 'job_title',
            'status', 'stage_name', 'share_date', 'created_at',
            # write-only
            'job_id', 'candidate_id', 'current_stage_id',
        ]
        read_only_fields = ['id', 'organization']

    def get_stage_name(self, obj):
        return obj.current_stage.name if obj.current_stage else None


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Full nested detail — candidate, job, stage, interview, submission."""
    current_stage      = StageBriefSerializer(read_only=True)
    job                = JobBriefSerializer(read_only=True)
    candidate          = CandidateBriefSerializer(read_only=True)
    interview_schedule = serializers.SerializerMethodField()
    client_submission  = serializers.SerializerMethodField()
    share_date         = DateParserField(required=False, allow_null=True)
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

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'is_deleted']

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

# ---------------------------------------------------------------------------
# Candidate serializers
# ---------------------------------------------------------------------------

class CandidateListSerializer(serializers.ModelSerializer):
    """Flat list — essential fields only, no nested applications."""
    uploaded_by_name    = serializers.SerializerMethodField()
    applications_count  = serializers.SerializerMethodField()
    duplicate_of_name   = serializers.SerializerMethodField()
    created_at          = DateParserDateTimeField(read_only=True)

    class Meta:
        model = Candidate
        fields = [
            'id', 'candidate_name', 'email', 'contact',
            'current_profile', 'current_company', 'experience',
            'current_location', 'notice_period',
            'current_ctc', 'expected_ctc',
            'resume_file_name', 'is_duplicate', 'duplicate_of_name',
            'applications_count', 'uploaded_by_name', 'created_at',
        ]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.name if obj.uploaded_by else None

    def get_applications_count(self, obj):
        return obj.applications.filter(is_deleted=False).count()

    def get_duplicate_of_name(self, obj):
        return obj.duplicate_of.candidate_name if obj.duplicate_of_id else None


class CandidateDetailSerializer(serializers.ModelSerializer):
    """Full detail — all fields + nested applications + uploader info."""
    applications         = ApplicationListSerializer(many=True, read_only=True)
    uploaded_by          = UserBriefSerializer(read_only=True)
    duplicate_of_detail  = CandidateBriefSerializer(source='duplicate_of', read_only=True)
    dob                  = DateParserField(required=False, allow_null=True)
    doc                  = DateParserField(required=False, allow_null=True)
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