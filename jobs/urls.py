from django.urls import path
from rest_framework.routers import DefaultRouter
from jobs.views import JobViewSet
from jobs.views_export import JobExportView, JobImportView

router = DefaultRouter()
router.register(r'', JobViewSet, basename='job')

urlpatterns = [
    path('export/', JobExportView.as_view(), name='job-export'),
    path('import/', JobImportView.as_view(), name='job-import'),
] + router.urls
