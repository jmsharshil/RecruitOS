from rest_framework import serializers
from accounts.models import User, Organization

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'created_at']

class UserBriefSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'avatar', 'role', 'organization']

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

class ManagerSerializer(serializers.ModelSerializer):
    jobs_count = serializers.IntegerField(read_only=True)
    recruiters_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'avatar', 'date_joined', 'role', 'jobs_count', 'recruiters_count']
        read_only_fields = ['id', 'date_joined', 'jobs_count', 'recruiters_count']

class RecruiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'avatar', 'date_joined', 'role', 'created_by']
        read_only_fields = ['id', 'date_joined', 'created_by']
