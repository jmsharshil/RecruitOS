from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# from drf_spectacular.Views import SpectacularAPIView,SpectacularSwaggerUIView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/v1/', include([
        path('',               include('accounts.urls')),
        path('clients/',       include('clients.urls')),
        path('jobs/',          include('jobs.urls')),
        path('candidates/',    include('candidates.urls')),
        path('notifications/', include('notifications.urls')),
        path('audit/',         include('audit.urls')),
    ])),

    # path('api/schema/', SpectacularAPIView.as_view(),        name='schema'),
    # path('api/docs/',   SpectacularSwaggerUIView.as_view(url_name='schema'), name='swagger-ui'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
