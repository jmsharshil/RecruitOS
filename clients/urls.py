from django.urls import path
from rest_framework.routers import DefaultRouter
from clients.views import ClientViewSet
from clients.views_export import ClientExportView, ClientImportView

router = DefaultRouter()
router.register(r'', ClientViewSet, basename='client')

urlpatterns = [
    path('export/', ClientExportView.as_view(), name='client-export'),
    path('import/', ClientImportView.as_view(), name='client-import'),
] + router.urls
