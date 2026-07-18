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
        return Notification.objects.filter(
            is_deleted=False,
            organization=self.request.user.organization,
            user=self.request.user
        )

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

    @action(detail=True, methods=['patch'], url_path='read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read = True
        notification.save()
        log_action(
            request.user, 
            'updated', 
            'Notification', 
            notification.id, 
            f"Marked notification '{notification.title}' as read"
        )
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().update(read=True)
        return Response({"message": "All notifications marked as read"})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(read=False).count()
        return Response({"count": count})
