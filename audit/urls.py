from rest_framework.routers import DefaultRouter
from audit.views import AuditLogViewSet

router = DefaultRouter()
router.register(r'', AuditLogViewSet, basename='auditlog')

urlpatterns = router.urls
