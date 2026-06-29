from rest_framework.routers import DefaultRouter
from jobs.views import JobViewSet

router = DefaultRouter()
router.register(r'', JobViewSet, basename='job')

urlpatterns = router.urls
