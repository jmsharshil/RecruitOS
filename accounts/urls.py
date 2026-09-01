from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import (
    LoginView, LogoutView, ForgotPasswordView, MeView, RegisterOrganizationView,
    UserViewSet, SetPinView,
    AdminDashboardView, ManagerDashboardView, RecruiterDashboardView, UnifiedDashboardView ,
    OrganizationEmailConfigView, EmailTemplateViewSet,
)
from accounts.views_google import GoogleLoginView, GoogleConfigView

router = DefaultRouter()
router.register(r'', UserViewSet, basename='user')

email_template_router = DefaultRouter()
email_template_router.register(r'email-templates', EmailTemplateViewSet, basename='email-template')

urlpatterns = [
    # Auth
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('auth/google-config/', GoogleConfigView.as_view(), name='google_config'),
    path('auth/register/', RegisterOrganizationView.as_view(), name='register-organization'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/set-pin/', SetPinView.as_view(), name='set-pin'),

    # Dashboard
    path('dashboard/admin/', AdminDashboardView.as_view(), name='dashboard-admin'),
    path('dashboard/manager/', ManagerDashboardView.as_view(), name='dashboard-manager'),
    path('dashboard/recruiter/', RecruiterDashboardView.as_view(), name='dashboard-recruiter'),

    path('dashboard/', UnifiedDashboardView.as_view(), name='dashboard-unified'),
    
    # Users
    path('users/', include(router.urls)),

    # Organization settings (email config + branding templates)
    path('org/email-config/', OrganizationEmailConfigView.as_view(), name='org-email-config'),
    path('org/', include(email_template_router.urls)),
]
