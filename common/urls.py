from django.urls import path
from .views import ExportFormatsView

urlpatterns = [
    path('export-formats/', ExportFormatsView.as_view(), name='export-formats'),
]
