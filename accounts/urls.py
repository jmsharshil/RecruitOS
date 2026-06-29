from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import (
    LoginView, LogoutView, ForgotPasswordView, MeView,
    ManagerViewSet, RecruiterViewSet,
    AdminDashboardView, ManagerDashboardView, RecruiterDashboardView
)

router = DefaultRouter()
router.register(r'managers', ManagerViewSet, basename='manager')
router.register(r'recruiters', RecruiterViewSet, basename='recruiter')

urlpatterns = [
    # Auth
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('auth/me/', MeView.as_view(), name='me'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    
    # Dashboard
    path('dashboard/admin/', AdminDashboardView.as_view(), name='dashboard-admin'),
    path('dashboard/manager/', ManagerDashboardView.as_view(), name='dashboard-manager'),
    path('dashboard/recruiter/', RecruiterDashboardView.as_view(), name='dashboard-recruiter'),
    
    # Users
    path('users/', include(router.urls)),
]
