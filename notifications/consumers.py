import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')

        if self.user and self.user.is_authenticated:
            self.group_name = f"user_{self.user.id}"

            # Join user's personal notification group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )

            await self.accept()
        else:
            # Reject the connection if not authenticated
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            # Leave user's personal notification group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # Receive message from room group
    async def notification_created(self, event):
        """
        Handler for the 'notification.created' event.
        The event dict must have a 'notification' payload.
        """
        payload = event.get('notification', {})
        
        # Send message to WebSocket
        await self.send_json({
            'event': 'notification.created',
            'notification': payload
        })
