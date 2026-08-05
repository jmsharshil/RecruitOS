from rest_framework import serializers
from audit.models import AuditLog

class AuditLogListSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            'id', 'timestamp', 'event', 'action', 'user_info',
            'method', 'status_code', 'path', 'entity', 'entity_id', 'details'
        ]
        read_only_fields = ['id', 'timestamp']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Fallback for event if it's an old manual log
        if not data.get('event'):
            data['event'] = data.get('details') or f"Action: {data.get('action', '')}"
            
        # Fallback for user role if it wasn't saved (old logs)
        if not data.get('user_info', {}).get('role') and getattr(instance, 'user', None):
            data['user_info']['role'] = instance.user.role
            
        # Ensure role is not null
        if data.get('user_info'):
            data['user_info']['role'] = data['user_info'].get('role') or "System"
        
        # Remove fields not needed by frontend grid
        data.pop('entity', None)
        data.pop('entity_id', None)
        data.pop('details', None)
        
        # Capitalize action
        if data.get('action'):
            data['action'] = data['action'].upper()
            
        return data

    def get_user_info(self, obj):
        return {
            "name": obj.user_name,
            "role": obj.user_role,
            "email": obj.user_email,
            "organization": obj.organization.name if obj.organization else None
        }

class AuditLogDetailSerializer(AuditLogListSerializer):
    class Meta(AuditLogListSerializer.Meta):
        fields = AuditLogListSerializer.Meta.fields + [
            'ip_address', 'user_agent', 'request_body', 'response_summary'
        ]
