from rest_framework.routers import DefaultRouter
from notifications.views import NotificationViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = router.urls
