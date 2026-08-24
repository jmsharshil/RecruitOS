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
    candidate_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    hiring_manager_name = serializers.SerializerMethodField()
    budget              = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    created_at          = DateParserDateTimeField(read_only=True)

    class Meta:
        model = Job
        fields = [
            'id', 'code', 'title', 'status',
            'location', 'min_experience', 'max_experience', 'budget',
            'hiring_for', 'candidate_count',
            'created_by_name', 'hiring_manager_name', 'created_at',
        ]

    def get_candidate_count(self, obj):
        return obj.applications.filter(is_deleted=False).count()

    def get_created_by_name(self, obj):
        return obj.created_by.name if obj.created_by else None

    def get_hiring_manager_name(self, obj):
        return obj.hiring_manager.name if obj.hiring_manager else None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        client_data = None
        if instance.client:
            client_data = {
                'id': str(instance.client.id),
                'name': instance.client.company_name,
                'team_member': None
            }
            if instance.team_member_id and isinstance(instance.client.team_members, list):
                for tm in instance.client.team_members:
                    if isinstance(tm, dict) and str(tm.get('id')) == str(instance.team_member_id):
                        client_data['team_member'] = {
                            'id': tm.get('id'),
                            'name': tm.get('name')
                        }
                        break
        
        ret['client'] = client_data
        return ret


# ---------------------------------------------------------------------------
# Detail serializer — full nested data for single job view
# ---------------------------------------------------------------------------
class JobDetailSerializer(serializers.ModelSerializer):
    stages              = serializers.SerializerMethodField()
    assigned_recruiters = UserBriefSerializer(many=True, read_only=True)
    candidate_count     = serializers.SerializerMethodField()
    created_by          = UserBriefSerializer(read_only=True)
    hiring_manager      = UserBriefSerializer(read_only=True)
    description         = serializers.CharField(required=False, allow_blank=True)
    created_at          = DateParserDateTimeField(read_only=True)
    updated_at          = DateParserDateTimeField(read_only=True)
    deleted_at          = DateParserDateTimeField(read_only=True, allow_null=True)

    # Write-only field for assigning recruiters
    assigned_recruiter_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True,
        queryset=User.objects.filter(role__in=['manager', 'recruiter', 'admin']),
        source='assigned_recruiters',
        required=False
    )

    # Write-only field for assigning hiring manager
    hiring_manager_id = serializers.PrimaryKeyRelatedField(
        write_only=True,
        queryset=User.objects.filter(role__in=['manager', 'admin']),
        source='hiring_manager',
        required=False,
        allow_null=True
    )

    def get_stages(self, obj):
        return StageSerializer(obj.stages.filter(is_deleted=False), many=True).data

    def get_candidate_count(self, obj):
        return obj.applications.filter(is_deleted=False).count()

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        client_data = None
        if instance.client:
            client_data = {
                'id': str(instance.client.id),
                'name': instance.client.company_name,
                'team_member': None
            }
            if instance.team_member_id and isinstance(instance.client.team_members, list):
                for tm in instance.client.team_members:
                    if isinstance(tm, dict) and str(tm.get('id')) == str(instance.team_member_id):
                        client_data['team_member'] = {
                            'id': tm.get('id'),
                            'name': tm.get('name'),
                            'email': tm.get('email')
                        }
                        break
        
        ret['client'] = client_data
        
        # Remove flat keys to avoid redundancy
        ret.pop('team_member_id', None)
        
        return ret

    class Meta:
        model = Job
        fields = [
            'id', 'code', 'title', 'description', 'description_file', 'skills', 'education',
            'min_experience', 'max_experience', 'location',
            'budget', 'hiring_for', 'client', 'status',
            'assigned_recruiters', 'assigned_recruiter_ids',
            'created_by', 'hiring_manager', 'hiring_manager_id',
            'stages', 'candidate_count', 'created_at', 'updated_at',
            'organization', 'is_deleted', 'deleted_at', 'team_member_id',
        ]
        read_only_fields = [
            'id', 'code', 'created_at', 'updated_at',
            'created_by', 'organization', 'is_deleted', 'deleted_at',
        ]
        extra_kwargs = {
            'team_member_id': {'write_only': True}
        }

    def validate(self, attrs):
        attrs['hiring_for'] = 'client'
        
        description_file = attrs.get('description_file')
        description = attrs.get('description')

        if not description and not description_file:
            raise serializers.ValidationError({"description": "You must either provide a plain text description or upload a description file."})

        if not attrs.get('client'):
            raise serializers.ValidationError({"client": "Client is required since all positions are client-scoped."})
        return attrs
