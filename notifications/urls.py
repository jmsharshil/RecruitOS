from rest_framework.routers import DefaultRouter
from notifications.views import NotificationViewSet, EmailLogViewSet

router = DefaultRouter()
router.register(r'email-logs', EmailLogViewSet, basename='email-log')
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = router.urls
