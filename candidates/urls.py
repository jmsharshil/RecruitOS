from django.urls import path
from rest_framework.routers import DefaultRouter
from candidates.views import (
    CandidateViewSet, ApplicationViewSet, CalendarEventsView, TalentPoolPublicUploadView,
)
from candidates.views_export import CandidateExportView, CandidateImportView

router = DefaultRouter()
router.register(r'', CandidateViewSet, basename='candidate')
router.register(r'applications', ApplicationViewSet, basename='application')

urlpatterns = [
    path('calendar/events/', CalendarEventsView.as_view(), name='calendar-events'),
    # Unified talent pool public upload — no longer scoped to a specific job
    path('upload/', TalentPoolPublicUploadView.as_view(), name='public-upload'),
    path('export/', CandidateExportView.as_view(), name='candidate-export'),
    path('import/', CandidateImportView.as_view(), name='candidate-import'),
] + router.urls
