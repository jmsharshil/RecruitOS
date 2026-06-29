from rest_framework import serializers
from jobs.models import Job, Stage
from accounts.serializers import UserBriefSerializer
from accounts.models import User

class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = ['id', 'name', 'order', 'color']

class StageBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = ['id', 'name', 'color']

class JobBriefSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    class Meta:
        model = Job
        fields = ['id', 'title', 'client_name']
    def get_client_name(self, obj):
        return obj.client.company_name if obj.client else None

class JobSerializer(serializers.ModelSerializer):
    stages = StageSerializer(many=True, read_only=True)
    assigned_recruiters = UserBriefSerializer(many=True, read_only=True)
    assigned_recruiter_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True,
        queryset=User.objects.filter(role='recruiter'),
        source='assigned_recruiters',
        required=False
    )
    candidate_count = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    created_by = UserBriefSerializer(read_only=True)

    def get_candidate_count(self, obj):
        return obj.candidates.filter(is_deleted=False).count()

    def get_client_name(self, obj):
        return obj.client.company_name if obj.client else None

    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = ['id', 'resume_upload_link', 'created_at', 'updated_at', 'created_by']
