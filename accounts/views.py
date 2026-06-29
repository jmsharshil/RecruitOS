import logging
from rest_framework import status, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User, UserRole
from accounts.serializers import UserBriefSerializer, ManagerSerializer, RecruiterSerializer, CustomTokenObtainPairSerializer
from common.permissions import IsAdmin, IsAdminOrManager, IsManager, IsRecruiter
from audit.utils import log_action
from audit.models import AuditLog
from audit.serializers import AuditLogSerializer
from jobs.models import Job, JobStatus
from clients.models import Client, ClientStatus
from candidates.models import Candidate, CandidateStatus, InterviewSchedule

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

class ManagerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = ManagerSerializer

    def get_queryset(self):
        return User.objects.filter(role=UserRole.MANAGER, organization=self.request.user.organization).annotate(
            jobs_count=Count('created_jobs', distinct=True),
            recruiters_count=Count('user', filter=Q(user__role=UserRole.RECRUITER), distinct=True)
        )

    def perform_create(self, serializer):
        user = serializer.save(role=UserRole.MANAGER, created_by=self.request.user, organization=self.request.user.organization)
        if 'password' in self.request.data:
            user.set_password(self.request.data['password'])
            user.save()
        log_action(self.request.user, 'created', 'User', user.id, f"Created manager '{user.name}'")

    def perform_destroy(self, instance):
        log_action(self.request.user, 'deleted', 'User', instance.id, f"Deleted manager '{instance.name}'")
        instance.delete()

class RecruiterViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrManager]
    serializer_class = RecruiterSerializer

    def get_queryset(self):
        qs = User.objects.filter(role=UserRole.RECRUITER, organization=self.request.user.organization)
        if self.request.user.role == UserRole.MANAGER:
            qs = qs.filter(created_by=self.request.user)
        return qs

    def perform_create(self, serializer):
        user = serializer.save(role=UserRole.RECRUITER, created_by=self.request.user, organization=self.request.user.organization)
        if 'password' in self.request.data:
            user.set_password(self.request.data['password'])
            user.save()
        log_action(self.request.user, 'created', 'User', user.id, f"Created recruiter '{user.name}'")

    def perform_destroy(self, instance):
        log_action(self.request.user, 'deleted', 'User', instance.id, f"Deleted recruiter '{instance.name}'")
        instance.delete()

# --- Dashboard Views ---

class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        this_month = now.replace(day=1, hour=0, minute=0, second=0)
        org = request.user.organization

        total_active_jobs = Job.objects.filter(status=JobStatus.OPEN, organization=org).count()
        candidates_this_month = Candidate.objects.filter(created_at__gte=this_month, is_deleted=False, organization=org).count()
        active_clients = Client.objects.filter(status=ClientStatus.ACTIVE, is_deleted=False, organization=org).count()
        
        recent_jobs = Job.objects.filter(organization=org).order_by('-created_at')[:5].values(
            'id', 'title', 'client__company_name', 'status', 'created_at'
        )

        top_recruiters = User.objects.filter(role=UserRole.RECRUITER, organization=org)[:5].values('id', 'name', 'avatar')
        recent_audit_logs = AuditLogSerializer(AuditLog.objects.filter(organization=org).order_by('-timestamp')[:5], many=True).data

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
        my_jobs = Job.objects.filter(created_by=request.user)
        my_open_jobs = my_jobs.filter(status=JobStatus.OPEN).count()
        candidates_in_pipeline = Candidate.objects.filter(job__in=my_jobs, is_deleted=False).exclude(status__in=[CandidateStatus.HIRED, CandidateStatus.REJECTED]).count()
        
        today = timezone.localdate()
        interviews_today = InterviewSchedule.objects.filter(candidate__job__in=my_jobs, date=today).count()
        
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
        assigned_jobs = Job.objects.filter(assigned_recruiters=request.user)
        assigned_jobs_count = assigned_jobs.count()
        total_candidates = Candidate.objects.filter(job__in=assigned_jobs, is_deleted=False).count()
        
        today = timezone.localdate()
        interviews_today = InterviewSchedule.objects.filter(candidate__job__in=assigned_jobs, date=today).count()
        
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
