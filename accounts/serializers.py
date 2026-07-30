from rest_framework import serializers
from accounts.models import User, Organization, UserRole, OrganizationEmailConfig, EmailTemplate


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'created_at']

class UserBriefSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'avatar', 'role', 'organization']

class OrganizationRegisterSerializer(serializers.Serializer):
    org_name       = serializers.CharField(max_length=200, required=True)
    admin_name     = serializers.CharField(max_length=150, required=True)
    admin_email    = serializers.EmailField(required=True)
    admin_password = serializers.CharField(write_only=True, required=True, min_length=8)

    def validate_org_name(self, value):
        if Organization.objects.filter(name=value).exists():
            raise serializers.ValidationError("An organization with this name already exists.")
        return value

    def validate_admin_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_admin_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        return value

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserBriefSerializer(self.user, context=self.context).data
        return data


# ---------------------------------------------------------------------------
# User list serializer — compact row for user management table
# ---------------------------------------------------------------------------
class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight list view. No nested organization object — just the name string.
    Annotated counts (jobs_count, recruiters_count) surfaced as flat ints.
    """
    organization_name = serializers.SerializerMethodField()
    jobs_count        = serializers.IntegerField(read_only=True, default=0)
    recruiters_count  = serializers.IntegerField(read_only=True, default=0)
    created_by_name   = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone', 'avatar', 'role',
            'organization_name', 'jobs_count', 'recruiters_count',
            'created_by_name', 'date_joined', 'is_active',
        ]

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def get_created_by_name(self, obj):
        return obj.created_by.name if obj.created_by else None


# ---------------------------------------------------------------------------
# User detail serializer — full nested detail (org object, created_by full)
# ---------------------------------------------------------------------------
class UserDetailSerializer(serializers.ModelSerializer):
    """
    Full detail for a single user view. Includes nested org and creator.
    """
    organization = OrganizationSerializer(read_only=True)
    created_by   = UserBriefSerializer(read_only=True)
    jobs_count       = serializers.IntegerField(read_only=True, default=0)
    recruiters_count = serializers.IntegerField(read_only=True, default=0)
    role = serializers.ChoiceField(
        choices=UserRole.choices,
        required=True,
        error_messages={'invalid_choice': "Role must be either 'manager' or 'recruiter'."}
    )

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone', 'avatar', 'role',
            'organization', 'created_by',
            'jobs_count', 'recruiters_count',
            'date_joined', 'is_active',
        ]
        read_only_fields = ['id', 'date_joined', 'created_by', 'organization', 'jobs_count', 'recruiters_count']

    def validate_role(self, value):
        if value not in [UserRole.MANAGER.value, UserRole.RECRUITER.value]:
            raise serializers.ValidationError("Role must be manager or recruiter.")
        return value

# ---------------------------------------------------------------------------
# Email Config + Template serializers
# ---------------------------------------------------------------------------

class OrganizationEmailConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for OrganizationEmailConfig.
    smtp_password is write-only and handled via set_smtp_password().
    smtp_password_encrypted is never exposed.
    """
    smtp_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        style={'input_type': 'password'},
        help_text='Leave blank to keep existing password unchanged.'
    )

    class Meta:
        model = OrganizationEmailConfig
        fields = [
            'id', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
            'from_email', 'from_name', 'use_tls', 'use_ssl', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        raw_password = validated_data.pop('smtp_password', '')
        instance = super().create(validated_data)
        if raw_password:
            instance.set_smtp_password(raw_password)
            instance.save(update_fields=['smtp_password_encrypted'])
        return instance

    def update(self, instance, validated_data):
        raw_password = validated_data.pop('smtp_password', None)
        instance = super().update(instance, validated_data)
        if raw_password is not None and raw_password != '':
            instance.set_smtp_password(raw_password)
            instance.save(update_fields=['smtp_password_encrypted'])
        return instance


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'template_key', 'logo_url', 'primary_color', 'secondary_color',
            'footer_text', 'custom_html', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
