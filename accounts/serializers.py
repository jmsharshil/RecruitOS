from rest_framework import serializers
from accounts.models import User, Organization, UserRole

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
    org_name = serializers.CharField(max_length=200, required=True)
    admin_name = serializers.CharField(max_length=150, required=True)
    admin_email = serializers.EmailField(required=True)
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
        data['user'] = UserBriefSerializer(self.user).data
        return data

class UserSerializer(serializers.ModelSerializer):
    jobs_count = serializers.IntegerField(read_only=True, required=False)
    recruiters_count = serializers.IntegerField(read_only=True, required=False)
    role = serializers.ChoiceField(
        choices=UserRole.choices,
        required=True,
        error_messages={
            'invalid_choice': "Role must be either 'manager' or 'recruiter'."
        }
    )

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'avatar', 'date_joined', 'role', 
                 'jobs_count', 'recruiters_count', 'created_by']
        read_only_fields = ['id', 'date_joined', 'created_by', 'jobs_count', 'recruiters_count']

    def validate_role(self, value):
        if value not in [UserRole.MANAGER.value, UserRole.RECRUITER.value]:
            raise serializers.ValidationError("Role must be manager or recruiter.")
        return value
