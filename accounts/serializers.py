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
    org_name = serializers.CharField(max_length=200)
    admin_name = serializers.CharField(max_length=150)
    admin_email = serializers.EmailField()
    admin_password = serializers.CharField(write_only=True)

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
