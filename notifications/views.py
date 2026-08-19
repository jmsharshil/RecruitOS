from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from audit.utils import log_action

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(
            is_deleted=False,
            organization=self.request.user.organization,
            user=self.request.user
        )
        
        unread = self.request.query_params.get('unread')
        if unread and unread.lower() in ['true', '1']:
            qs = qs.filter(read=False)
            
        limit = self.request.query_params.get('limit')
        if limit and limit.isdigit():
            qs = qs[:int(limit)]
            
        return qs

    def perform_create(self, serializer):
        notification = serializer.save(
            user=self.request.user,
            organization=self.request.user.organization
        )
        log_action(
            self.request.user, 
            'created', 
            'Notification', 
            notification.id, 
            f"Created notification '{notification.title}'"
        )

    def perform_update(self, serializer):
        notification = serializer.save()
        log_action(
            self.request.user, 
            'updated', 
            'Notification', 
            notification.id, 
            f"Updated notification '{notification.title}'"
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(
            self.request.user, 
            'deleted', 
            'Notification', 
            instance.id, 
            f"Deleted notification '{instance.title}'"
        )

    @action(detail=False, methods=['patch'], url_path='mark-read')
    def bulk_mark_read(self, request):
        """
        API to mark one or multiple notifications as read/unread.
        Payload:
        {
            "id": "uuid", OR "ids": ["uuid1", "uuid2"],
            "is_read": true
        }
        """
        data = request.data
        ids = data.get('ids', [])
        single_id = data.get('id')
        is_read = data.get('is_read', True)

        if single_id and single_id not in ids:
            ids.append(single_id)
            
        if not ids:
            return Response({"error": "Please provide 'id' or 'ids' in payload"}, status=400)
            
        updated_count = self.get_queryset().filter(id__in=ids).update(read=is_read)
        return Response({"message": f"Successfully updated {updated_count} notifications."})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().update(read=True)
        return Response({"message": "All notifications marked as read"})
