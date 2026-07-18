from rest_framework import serializers
from candidates.models import Candidate, Application, InterviewSchedule, ClientSubmission
from jobs.models import Job, Stage
from jobs.serializers import StageBriefSerializer, JobBriefSerializer
from accounts.serializers import UserBriefSerializer


class CandidateBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = ['id', 'candidate_name', 'email', 'contact', 'current_profile', 
                 'current_company', 'experience', 'resume_file_name']


class InterviewScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ['id', 'application', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']


class ClientSubmissionSerializer(serializers.ModelSerializer):
    sent_by = UserBriefSerializer(read_only=True)
    class Meta:
        model = ClientSubmission
        fields = '__all__'
        read_only_fields = ['id', 'application', 'sent_at', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']

class ApplicationSerializer(serializers.ModelSerializer):
    current_stage = StageBriefSerializer(read_only=True)
    job = JobBriefSerializer(read_only=True)
    candidate = CandidateBriefSerializer(read_only=True)
    interview_schedule = serializers.SerializerMethodField()
    client_submission = serializers.SerializerMethodField()
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
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_deleted', 'deleted_at', 'organization']

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


class CandidateSerializer(serializers.ModelSerializer):
    applications = ApplicationSerializer(many=True, read_only=True)
    uploaded_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = Candidate
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_deleted', 'deleted_at', 'organization', 'uploaded_by']
