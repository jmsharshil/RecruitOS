from django.urls import path
from rest_framework.routers import DefaultRouter
from candidates.views import CandidateViewSet, CalendarEventsView, PublicUploadView
from candidates.views_export import CandidateExportView, CandidateImportView

router = DefaultRouter()
router.register(r'', CandidateViewSet, basename='candidate')

urlpatterns = [
    path('calendar/events/', CalendarEventsView.as_view(), name='calendar-events'),
    path('upload/<uuid:job_id>/', PublicUploadView.as_view(), name='public-upload'),
    path('export/', CandidateExportView.as_view(), name='candidate-export'),
    path('import/', CandidateImportView.as_view(), name='candidate-import'),
] + router.urls
