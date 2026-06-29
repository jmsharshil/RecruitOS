from rest_framework import serializers
from candidates.models import Candidate, InterviewSchedule, ClientSubmission
from jobs.models import Job, Stage
from jobs.serializers import StageBriefSerializer, JobBriefSerializer

class InterviewScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ['id', 'candidate', 'created_at', 'updated_at']

class ClientSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientSubmission
        fields = '__all__'
        read_only_fields = ['id', 'candidate', 'sent_at', 'sent_by']

class CandidateSerializer(serializers.ModelSerializer):
    current_stage = StageBriefSerializer(read_only=True)
    job = JobBriefSerializer(read_only=True)
    job_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Job.objects.all(), source='job'
    )
    current_stage_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Stage.objects.all(), source='current_stage',
        required=False, allow_null=True
    )
    interview_schedule = InterviewScheduleSerializer(read_only=True)
    client_submission = ClientSubmissionSerializer(read_only=True)

    class Meta:
        model = Candidate
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'is_deleted', 'deleted_at']
