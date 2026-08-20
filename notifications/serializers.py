from rest_framework import serializers
from notifications.models import Notification

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
