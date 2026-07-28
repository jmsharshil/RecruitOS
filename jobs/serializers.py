from rest_framework import serializers
from jobs.models import Job, Stage
from accounts.serializers import UserBriefSerializer
from accounts.models import User
from common.serializers import DateParserField, DateParserDateTimeField

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

# ---------------------------------------------------------------------------
# List serializer — flat, no nested queries, fast for paginated lists
# ---------------------------------------------------------------------------
class JobListSerializer(serializers.ModelSerializer):
    client_name     = serializers.SerializerMethodField()
    candidate_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    target_closing_date = DateParserField(read_only=True)
    budget              = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    skill_criteria      = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    created_at          = DateParserDateTimeField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'code', 'title', 'status', 'priority', 'job_mode', 'job_type',
            'location', 'openings', 'min_experience', 'max_experience', 'budget',
            'skill_criteria',
            'hiring_for', 'client_name', 'candidate_count',
            'target_closing_date', 'created_by_name', 'created_at',
        ]

    def get_client_name(self, obj):
        return obj.client.company_name if obj.client else None

    def get_candidate_count(self, obj):
        return obj.applications.filter(is_deleted=False).count()

    def get_created_by_name(self, obj):
        return obj.created_by.name if obj.created_by else None


# ---------------------------------------------------------------------------
# Detail serializer — full nested data for single job view
# ---------------------------------------------------------------------------
class JobDetailSerializer(serializers.ModelSerializer):
    stages              = serializers.SerializerMethodField()
    assigned_recruiters = UserBriefSerializer(many=True, read_only=True)
    candidate_count     = serializers.SerializerMethodField()
    client_name         = serializers.SerializerMethodField()
    created_by          = UserBriefSerializer(read_only=True)
    target_closing_date = DateParserField(required=False, allow_null=True)
    created_at          = DateParserDateTimeField(read_only=True)
    updated_at          = DateParserDateTimeField(read_only=True)
    deleted_at          = DateParserDateTimeField(read_only=True, allow_null=True)

    # Write-only field for assigning recruiters
    assigned_recruiter_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True,
        queryset=User.objects.filter(role='recruiter'),
        source='assigned_recruiters',
        required=False
    )

    def get_stages(self, obj):
        return StageSerializer(obj.stages.filter(is_deleted=False), many=True).data

    def get_candidate_count(self, obj):
        return obj.applications.filter(is_deleted=False).count()

    def get_client_name(self, obj):
        return obj.client.company_name if obj.client else None

    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = [
            'id', 'code', 'created_at', 'updated_at',
            'created_by', 'organization', 'is_deleted', 'deleted_at',
        ]
