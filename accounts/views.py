import logging
from rest_framework import status, permissions, viewsets, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User, UserRole, Organization
from accounts.serializers import (
    UserBriefSerializer, 
    UserSerializer, 
    CustomTokenObtainPairSerializer,
    OrganizationRegisterSerializer
)
from common.permissions import IsAdmin, IsAdminOrManager, IsManager, IsRecruiter, IsOwnerOrAdmin
from audit.utils import log_action
from audit.models import AuditLog
from audit.serializers import AuditLogSerializer
from jobs.models import Job, JobStatus
from clients.models import Client, ClientStatus
from candidates.models import Application, Candidate, CandidateStatus, InterviewSchedule

logger = logging.getLogger(__name__)

# --- Auth Views ---

class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Validation failed", "field_errors": {"email": ["This field is required."]}}, status=400)
        
        logger.info(f"[SIMULATION] Password reset link sent to {email}")
        return Response({"message": "If an account with that email exists, we have sent a password reset link."})


class RegisterOrganizationView(APIView):
    """
    Register a new organization with an admin user.
    This is the entry point for new organizations.
    Endpoint: /api/v1/auth/register/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = OrganizationRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "error": "Validation failed", 
                "field_errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        org_name = serializer.validated_data['org_name']
        admin_name = serializer.validated_data['admin_name']
        admin_email = serializer.validated_data['admin_email']
        admin_password = serializer.validated_data['admin_password']

        # Check if organization or user already exists
        if Organization.objects.filter(name=org_name).exists():
            return Response({
                "error": "An organization with this name already exists."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=admin_email).exists():
            return Response({
                "error": "A user with this email already exists."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create organization
            organization = Organization.objects.create(name=org_name)
            
            # Create admin user
            admin_user = User.objects.create_user(
                email=admin_email,
                name=admin_name,
                role=UserRole.ADMIN,
                password=admin_password,
                organization=organization
            )
            
            logger.info(f"New organization created: {org_name} with admin {admin_email}")
            
            # Generate tokens
            refresh = RefreshToken.for_user(admin_user)
            
            return Response({
                "message": "Organization and admin account created successfully",
                "organization": {
                    "id": str(organization.id),
                    "name": organization.name
                },
                "user": {
                    "id": str(admin_user.id),
                    "name": admin_user.name,
                    "email": admin_user.email,
                    "role": admin_user.role,
                    "organization": organization.name
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token)
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Organization registration failed: {str(e)}")
            return Response({
                "error": "Failed to create organization. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserBriefSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserBriefSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# --- User Management Views ---

class UserViewSet(viewsets.ModelViewSet):
    """
    Singular API to create/list both Managers and Recruiters.
    - Admins can create managers and recruiters.
    - Managers can only create recruiters.
    - Use 'role' field in POST body: 'manager' or 'recruiter'.
    - Endpoint: /api/v1/users/
    """
    permission_classes = [IsAdminOrManager, IsOwnerOrAdmin]
    serializer_class = UserSerializer

    def get_queryset(self):
        qs = User.objects.filter(
            role__in=[UserRole.MANAGER, UserRole.RECRUITER],
            organization=self.request.user.organization
        ).select_related('created_by')

        # Always annotate counts for consistency with serializer (0 for recruiters)
        qs = qs.annotate(
            jobs_count=Count('created_jobs', distinct=True),
            recruiters_count=Count(
                'created_users', 
                filter=Q(created_users__role=UserRole.RECRUITER), 
                distinct=True
            )
        )

        if self.request.user.role == UserRole.MANAGER:
            # Managers only see their own recruiters
            qs = qs.filter(role=UserRole.RECRUITER, created_by=self.request.user)
        return qs

    def perform_create(self, serializer):
        role = serializer.validated_data.get('role')
        if role == UserRole.MANAGER.value and self.request.user.role != UserRole.ADMIN.value:
            raise PermissionDenied("Only administrators can create manager accounts.")
        
        user = serializer.save(
            created_by=self.request.user, 
            organization=self.request.user.organization
        )
        if 'password' in self.request.data:
            user.set_password(self.request.data['password'])
            user.save()
        log_action(self.request.user, 'created', 'User', user.id, f"Created {role} '{user.name}'")

    def perform_destroy(self, instance):
        log_action(
            self.request.user, 
            'deleted', 
            'User', 
            instance.id, 
            f"Deleted {instance.role} '{instance.name}'"
        )
        instance.delete()

# --- Dashboard Views ---

class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        this_month = now.replace(day=1, hour=0, minute=0, second=0)
        org = request.user.organization

        total_active_jobs = Job.objects.filter(
            is_deleted=False, status=JobStatus.OPEN, organization=org
        ).count()
        candidates_this_month = Candidate.objects.filter(
            created_at__gte=this_month, is_deleted=False, organization=org
        ).count()
        active_clients = Client.objects.filter(
            is_deleted=False, status=ClientStatus.ACTIVE, organization=org
        ).count()
        
        recent_jobs = Job.objects.filter(
            is_deleted=False, organization=org
        ).order_by('-created_at')[:5].values(
            'id', 'title', 'client__company_name', 'status', 'created_at'
        )

        top_recruiters = User.objects.filter(
            role=UserRole.RECRUITER, organization=org
        )[:5].values('id', 'name', 'avatar')
        recent_audit_logs = AuditLogSerializer(
            AuditLog.objects.filter(organization=org).order_by('-timestamp')[:5], 
            many=True
        ).data

        return Response({
            "stats": {
                "total_active_jobs": total_active_jobs,
                "candidates_this_month": candidates_this_month,
                "active_clients": active_clients,
                "open_positions": total_active_jobs,
            },
            "recent_jobs": recent_jobs,
            "top_recruiters": top_recruiters,
            "recent_audit_logs": recent_audit_logs
        })

class ManagerDashboardView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        org = request.user.organization
        my_jobs = Job.objects.filter(
            is_deleted=False, 
            created_by=request.user, 
            organization=org
        )
        my_open_jobs = my_jobs.filter(status=JobStatus.OPEN).count()
        candidates_in_pipeline = Application.objects.filter(
            job__in=my_jobs, 
            is_deleted=False
        ).exclude(
            status__in=[CandidateStatus.HIRED, CandidateStatus.REJECTED]
        ).count()
        
        today = timezone.localdate()
        interviews_today = InterviewSchedule.objects.filter(
            is_deleted=False, 
            application__job__in=my_jobs, 
            date=today
        ).count()
        
        return Response({
            "stats": {
                "my_open_jobs": my_open_jobs,
                "candidates_in_pipeline": candidates_in_pipeline,
                "interviews_today": interviews_today,
                "pending_client_submissions": 0
            },
            "my_jobs": my_jobs.order_by('-created_at')[:5].values('id', 'title', 'status'),
            "todays_interviews": [],
            "pipeline_summary": []
        })

class RecruiterDashboardView(APIView):
    permission_classes = [IsRecruiter]

    def get(self, request):
        org = request.user.organization
        assigned_jobs = Job.objects.filter(
            is_deleted=False, 
            assigned_recruiters=request.user,
            organization=org
        )
        assigned_jobs_count = assigned_jobs.count()
        total_candidates = Application.objects.filter(
            job__in=assigned_jobs, 
            is_deleted=False
        ).count()
        
        today = timezone.localdate()
        interviews_today = InterviewSchedule.objects.filter(
            is_deleted=False, 
            application__job__in=assigned_jobs, 
            date=today
        ).count()
        
        return Response({
            "stats": {
                "assigned_jobs": assigned_jobs_count,
                "total_candidates": total_candidates,
                "resumes_this_week": 0,
                "interviews_today": interviews_today
            },
            "assigned_jobs": assigned_jobs.order_by('-created_at')[:5].values('id', 'title', 'status'),
            "recent_candidates": [],
            "todays_interviews": []
        })
