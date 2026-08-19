import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def create_notification(**kwargs):
        """
        Creates a notification in PostgreSQL and immediately broadcasts
        it to the recipient's personal WebSocket group.
        
        kwargs must contain valid fields for the Notification model, e.g.:
        user, organization, title, message, type, name, event, process, link
        """
        # 1. Persist the notification in the database
        notification = Notification.objects.create(**kwargs)
        
        # 2. Publish real-time event
        try:
            channel_layer = get_channel_layer()
            group_name = f"user_{notification.user_id}"
            
            payload = {
                "id": str(notification.id),
                "title": notification.title,
                "message": notification.message,
                "type": notification.type,
                "name": notification.name,
                "event": notification.event,
                "process": notification.process,
                "link": notification.link,
                "created_at": notification.created_at.isoformat(),
                "is_read": notification.read,
            }
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "notification.created",
                    "notification": payload
                }
            )
        except Exception as e:
            # Swallow exceptions to ensure business logic never fails due to WebSockets
            logger.error(f"Failed to broadcast real-time notification {notification.id}: {e}")
            
        return notification
