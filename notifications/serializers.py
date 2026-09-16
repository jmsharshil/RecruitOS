from rest_framework import serializers
from notifications.models import Notification, EmailLog

class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(source='read', required=False)

    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['id', 'user', 'created_at', 'organization']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Frontend expects the key to be "from", which is a reserved keyword in Python
        ret['from'] = None
        if instance.from_user:
            ret['from'] = {
                'id': str(instance.from_user.id),
                'name': instance.from_user.name,
                'email': instance.from_user.email,
            }
        # Optionally remove the original from_user flat ID if it's there
        ret.pop('from_user', None)
        return ret

class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = '__all__'
        read_only_fields = ['id', 'sender', 'organization', 'sent_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        # Format sender info
        if instance.sender:
            ret['sender_info'] = {
                'id': str(instance.sender.id),
                'name': instance.sender.name,
                'email': instance.sender.email,
                'role': getattr(instance.sender.role, 'name', None) if getattr(instance.sender, 'role', None) else None
            }
        else:
            ret['sender_info'] = None
            
        # Format candidate info
        if instance.candidate:
            ret['candidate_info'] = {
                'id': str(instance.candidate.id),
                'name': f"{instance.candidate.first_name} {instance.candidate.last_name}".strip() if hasattr(instance.candidate, 'first_name') else instance.candidate.name,
                'email': instance.candidate.email if hasattr(instance.candidate, 'email') else None
            }
        else:
            ret['candidate_info'] = None
            
        return ret
