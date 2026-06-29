from rest_framework import serializers
from accounts.models import User

class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'avatar', 'role']

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
