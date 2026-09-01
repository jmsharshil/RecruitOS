import logging
from rest_framework import status, permissions, viewsets, serializers, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, UserRole, Organization, OrganizationEmailConfig, EmailTemplate
from accounts.serializers import (
    UserBriefSerializer,
    UserDetailSerializer,
    UserListSerializer,
    CustomTokenObtainPairSerializer,
    OrganizationRegisterSerializer,
    OrganizationEmailConfigSerializer,
    EmailTemplateSerializer,
)
from common.permissions import IsAdmin, IsAdminOrManager, IsManager, IsRecruiter, IsOwnerOrAdmin
from audit.utils import log_action
from audit.models import AuditLog
from audit.serializers import AuditLogListSerializer
from jobs.models import Job, JobStatus
from clients.models import Client, ClientStatus
from candidates.models import Application, Candidate, CandidateStatus, InterviewSchedule
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from accounts.email_utils import send_org_email
from django.conf import settings

logger = logging.getLogger(__name__)


def send_set_pin_email(user, sender_email=None):
    """
    Send invitation email with magic link for user to set their PIN.
    Uses org-aware SMTP via send_org_email(), which now **enforces fallback**
    to global credentials (.env / settings.EMAIL_*) on any SMTP auth failure,
    inactive config, or missing OrganizationEmailConfig. This fixes delivery
    failures (e.g. Outlook 535 auth errors) while preserving per-org branding.
    """
    # token = default_token_generator.make_token(user)
    # uid = urlsafe_base64_encode(force_bytes(user.pk))
    # url = f"{settings.FRONTEND_URL}/set-pin?uid={uid}&token={token}"
    frontend_url = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
    url = f"{frontend_url}/login"

    org = getattr(user, 'organization', None)
    plain_message = (
        f"Welcome to the team! Your account has been created successfully, and you can now access the platform using your login credentials.\n"
        f"We’re excited to have you on board and look forward to working with you.\n\n"
        f"Link: {url}"
    )

    context = {
        'user': user,
        'url': url,
        'plain_message': plain_message,
    }

    try:
        send_org_email(
            organization=org,
            subject='Welcome to DSP Eminence Consulting Services',
            template_name='set_pin',
            context=context,
            recipient_list=[user.email],
            from_email_override=sender_email,
        )
        logger.info(f"Invitation email sent to {user.email} with link to {url}")
    except Exception as e:
        logger.error(f"Failed to send invitation email to {user.email} (both org and global fallback failed): {str(e)}")
def send_forgot_password_email(user):
    """
    Send forgot password/PIN email with magic link for user to reset their PIN.
    Uses the same link configuration as set_pin but a custom forgot_password template.
    """
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    frontend_url = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
    url = f"{frontend_url}/set-pin?uid={uid}&token={token}"

    org = getattr(user, 'organization', None)
    plain_message = (
        f"Your request to reset your PIN has been received. Please use the secure link/process provided to create your new PIN.\n\n"
        f"Link: {url}"
    )

    context = {
        'user': user,
        'uid': uid,
        'token': token,
        'domain': frontend_url,
        'url': url,
        'plain_message': plain_message,
    }

    try:
        send_org_email(
            organization=org,
            subject=f'Reset Your PIN — {getattr(org, "name", "RecruitOS")}',
            template_name='forgot_password',
            context=context,
            recipient_list=[user.email],
        )
        logger.info(f"Forgot PIN email sent to {user.email} with link to {url}")
    except Exception as e:
        logger.error(f"Failed to send forgot PIN email to {user.email} (both org and global fallback failed): {str(e)}")


def forgot_password_email(user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    url = f"{settings.FRONTEND_URL}/set-pin?uid={uid}&token={token}"

    org = getattr(user, 'organization', None)
    plain_message = (
        f"Your password-change request has been initiated successfully. Please complete the process using the instructions provided.\n"
        f"For security, do not share your password with anyone.\n\n"
        f"Link: {url}"
    )

    context = {
        'user': user,
        'uid': uid,
        'token': token,
        'url': url,
        'plain_message': plain_message,
    }

    try:
        send_org_email(
            organization=org,
            subject=f'Change Password',
            template_name='change_password',
            context=context,
            recipient_list=[user.email],
        )
        logger.info(f"Password change email sent to {user.email} with link to {url}")
    except Exception as e:
        logger.error(f"Failed to send password change email to {user.email} (both org and global fallback failed): {str(e)}")

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
        
        email_clean = str(email).strip().lower()
        user = User.objects.filter(email__iexact=email_clean).first()
        if user:
            send_forgot_password_email(user)
        else:
            logger.info(f"Forgot PIN request received for non-existent email: {email_clean}")
        
        return Response({"message": "If an account with that email exists, we have sent a password reset link."})


class SetPinView(APIView):
    """
    API to set PIN (which sets the user's password).
    Called from the link in the invitation email.
    Uses uid + token for security (same as Django password reset).
    Endpoint: /api/v1/auth/set-pin/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid') or request.query_params.get('uid')
        token = request.data.get('token') or request.query_params.get('token')
        pin = request.data.get('pin')
        confirm_pin = request.data.get('confirm_pin')

        if not all([uidb64, token, pin]):
            return Response({
                "error": "Validation failed",
                "field_errors": {"uid": ["uid, token, and pin are required."]}
            }, status=400)

        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid user link"}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired token. Please request a new PIN setup link."}, status=400)

        pin_str = str(pin).strip()
        if len(pin_str) < 4:
            return Response({
                "error": "Validation failed",
                "field_errors": {"pin": ["PIN must be at least 4 characters long."]}
            }, status=400)

        if pin != confirm_pin:
            return Response({
                "error": "Validation failed",
                "field_errors": {"confirm_pin": ["PIN and confirm PIN do not match."]}
            }, status=400)

        # Set the password to the provided PIN (allows login with it)
        user.set_password(pin_str)
        user.save()
        
        logger.info(f"PIN successfully set for user {user.email}")
        log_action(None, 'updated', 'User', user.id, f"User set their PIN via email link")
        
        return Response({
            "message": "PIN set successfully. You can now log in using your PIN."
        }, status=status.HTTP_200_OK)


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
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'email']

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        return UserDetailSerializer

    def get_queryset(self):
        qs = User.objects.filter(
            role__in=[UserRole.ADMIN, UserRole.MANAGER, UserRole.RECRUITER],
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
            # Managers see their own recruiters OR managers/recruiters created by the Admin
            qs = qs.filter(
                Q(role=UserRole.RECRUITER, created_by=self.request.user) |
                Q(created_by__role=UserRole.ADMIN) |
                Q(created_by__isnull=True)
            )
        return qs

    def perform_create(self, serializer):
        role = serializer.validated_data.get('role')
        if role == UserRole.MANAGER.value and self.request.user.role != UserRole.ADMIN.value:
            raise PermissionDenied("Only administrators can create manager accounts.")
        
        user = serializer.save(
            created_by=self.request.user, 
            organization=self.request.user.organization
        )
        # if 'password' in self.request.data:
        #     user.set_password(self.request.data['password'])
        #     user.save()
        send_set_pin_email(user, self.request.user.email)
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
        recent_audit_logs = AuditLogListSerializer(
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
        interviews_today_qs = InterviewSchedule.objects.filter(
            is_deleted=False, 
            application__job__in=my_jobs, 
            date=today,
            application__is_deleted=False
        ).select_related('application__candidate', 'application__job')
        
        interviews_today = []
        for interview in interviews_today_qs:
            interviews_today.append({
                "candidate_name": interview.application.candidate.candidate_name,
                "job_title": interview.application.job.title,
                "time": str(interview.time),
                "mode": interview.mode,
                "notes": interview.notes or ""
            })
        interviews_today_count = len(interviews_today)
        
        pending_client_submissions = Application.objects.filter(
            job__in=my_jobs,
            status=CandidateStatus.SENT_TO_CLIENT,
            is_deleted=False,
            organization=org
        ).count()
        
        # Pipeline summary by status
        pipeline_summary = list(
            Application.objects.filter(
                job__in=my_jobs, 
                is_deleted=False,
                organization=org
            ).values('status').annotate(count=Count('id')).order_by('status')
        )
        
        # Recent applications
        recent_applications = Application.objects.filter(
            job__in=my_jobs, 
            is_deleted=False,
            organization=org
        ).select_related('candidate', 'current_stage', 'job').order_by('-created_at')[:5]
        recent = [{
            "candidate": app.candidate.candidate_name,
            "job": app.job.title,
            "status": app.status,
            "stage": getattr(app.current_stage, 'name', 'Screening')
        } for app in recent_applications]
        
        return Response({
            "stats": {
                "my_open_jobs": my_open_jobs,
                "candidates_in_pipeline": candidates_in_pipeline,
                "interviews_today": interviews_today_count,
                "pending_client_submissions": pending_client_submissions
            },
            "my_jobs": list(my_jobs.order_by('-created_at')[:5].values('id', 'title', 'status', 'openings')),
            "todays_interviews": interviews_today,
            "pipeline_summary": pipeline_summary,
            "recent_applications": recent
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
        interviews_today_qs = InterviewSchedule.objects.filter(
            is_deleted=False, 
            application__job__in=assigned_jobs, 
            date=today,
            application__is_deleted=False
        ).select_related('application__candidate', 'application__job')
        
        interviews_today = [{
            "candidate_name": interview.application.candidate.candidate_name,
            "job_title": interview.application.job.title,
            "time": str(interview.time),
            "mode": interview.mode,
            "notes": interview.notes or ""
        } for interview in interviews_today_qs]
        interviews_today_count = len(interviews_today)
        
        this_week = timezone.now() - timedelta(days=7)
        resumes_this_week = Application.objects.filter(
            job__in=assigned_jobs,
            created_at__gte=this_week,
            is_deleted=False,
            organization=org
        ).count()
        
        # Recent candidates/applications for recruiter
        recent_applications = Application.objects.filter(
            job__in=assigned_jobs, 
            is_deleted=False,
            organization=org
        ).select_related('candidate', 'job', 'current_stage').order_by('-created_at')[:5]
        recent_candidates = [{
            "name": app.candidate.candidate_name,
            "email": app.candidate.email,
            "status": app.status,
            "job": app.job.title,
            "stage": app.current_stage.name if app.current_stage else "Screening"
        } for app in recent_applications]
        
        return Response({
            "stats": {
                "assigned_jobs": assigned_jobs_count,
                "total_candidates": total_candidates,
                "resumes_this_week": resumes_this_week,
                "interviews_today": interviews_today_count
            },
            "assigned_jobs": list(assigned_jobs.order_by('-created_at')[:5].values('id', 'title', 'status', 'openings')),
            "recent_candidates": recent_candidates,
            "todays_interviews": interviews_today
        })

class UnifiedDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization
        
        # 1. Total Candidates
        total_candidates = Candidate.objects.filter(is_deleted=False, organization=org).count()
        
        # 2. Active Jobs grouped by status
        job_qs = Job.objects.filter(is_deleted=False, organization=org)
        
        if user.role == UserRole.MANAGER:
            job_qs = job_qs.filter(created_by=user)
        elif user.role == UserRole.RECRUITER:
            job_qs = job_qs.filter(assigned_recruiters=user)

        active_jobs = list(job_qs.values('status').annotate(count=Count('id')))
        
        # 3. Interviews Upcoming (today to 3 days)
        today = timezone.localdate()
        three_days_later = today + timedelta(days=3)
        
        interview_qs = InterviewSchedule.objects.filter(
            is_deleted=False,
            application__job__in=job_qs,
            date__range=[today, three_days_later],
            application__is_deleted=False
        ).select_related('application__candidate', 'application__job', 'application__current_stage')
        
        upcoming_interviews = []
        for interview in interview_qs:
            upcoming_interviews.append({
                "candidate_name": interview.application.candidate.candidate_name,
                "job_title": interview.application.job.title,
                "date": str(interview.date),
                "time": str(interview.time),
                "round": getattr(interview.application.current_stage, 'name', 'Interview'),
                "mode": interview.mode,
                "interviewer_name": interview.interviewer_name or ""
            })
            
        # 4. Active Clients
        active_clients = Client.objects.filter(is_deleted=False, status=ClientStatus.ACTIVE, organization=org).count()
        
        # 5. Unread Activity
        from notifications.models import Notification
        unread_notifications = Notification.objects.filter(user=user, read=False, is_deleted=False).order_by('-created_at')[:10]
        unread_activity = []
        for notif in unread_notifications:
            unread_activity.append({
                "title": notif.title,
                "message": notif.message,
                "type": notif.type,
                "created_at": notif.created_at
            })
            
        # 6. Hires by Client
        hires_qs = Application.objects.filter(
            status=CandidateStatus.HIRED, 
            is_deleted=False, 
            job__in=job_qs
        ).values('job__client__company_name').annotate(hires_count=Count('id')).order_by('-hires_count')
        
        hires_by_client = []
        for h in hires_qs:
            if h['job__client__company_name']:
                hires_by_client.append({
                    "client_name": h['job__client__company_name'],
                    "hires_count": h['hires_count']
                })

        # --- NEW METRICS IMPLEMENTATION ---
        
        # 1. Funnel Trend (Last 7 Months)
        from django.db.models.functions import TruncMonth
        from dateutil.relativedelta import relativedelta
        import calendar
        
        end_date = timezone.now()
        start_date = end_date - relativedelta(months=6)
        
        # Sourced: Applications created in last 7 months
        sourced_qs = Application.objects.filter(
            is_deleted=False, 
            job__in=job_qs, 
            created_at__gte=start_date
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id'))
        
        # Interviewed: InterviewSchedules created in last 7 months
        interviewed_qs = InterviewSchedule.objects.filter(
            is_deleted=False, 
            application__job__in=job_qs, 
            created_at__gte=start_date
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id'))
        
        sourced_dict = {item['month'].strftime('%b'): item['count'] for item in sourced_qs if item['month']}
        interviewed_dict = {item['month'].strftime('%b'): item['count'] for item in interviewed_qs if item['month']}
        
        funnel_trend = []
        for i in range(6, -1, -1):
            d = end_date - relativedelta(months=i)
            month_name = d.strftime('%b')
            funnel_trend.append({
                "month": month_name,
                "sourced": sourced_dict.get(month_name, 0),
                "interviewed": interviewed_dict.get(month_name, 0)
            })
            
        # 2. Efficiency Metrics
        from django.db.models import F, Avg
        hired_apps = Application.objects.filter(is_deleted=False, job__in=job_qs, status=CandidateStatus.HIRED)
        if hired_apps.exists():
            avg_delta = hired_apps.aggregate(avg_time=Avg(F('updated_at') - F('created_at')))['avg_time']
            time_to_hire_days = avg_delta.days if avg_delta else 0
            time_to_hire = f"{time_to_hire_days} Days"
        else:
            time_to_hire = "0 Days"
            
        offered_count = Application.objects.filter(is_deleted=False, job__in=job_qs, status__in=[CandidateStatus.OFFERED, CandidateStatus.HIRED, CandidateStatus.JOINED]).count()
        accepted_count = Application.objects.filter(is_deleted=False, job__in=job_qs, status__in=[CandidateStatus.HIRED, CandidateStatus.JOINED]).count()
        offer_acc = int((accepted_count / offered_count) * 100) if offered_count > 0 else 0
        offer_acceptance = f"{offer_acc}%"
        
        efficiency_metrics = {
            "time_to_hire": time_to_hire,
            "offer_acceptance": offer_acceptance,
            "cost_per_hire": "₹24,500",
            "diversity_ratio": "34%"
        }
        
        # 3. Top Sourcing Channels (Mocked for now)
        top_sourcing_channels = [
            {"channel": "Naukri.com", "count": 45},
            {"channel": "LinkedIn", "count": 32},
            {"channel": "Employee Referrals", "count": 18},
            {"channel": "Instahyre", "count": 12},
            {"channel": "Campus Drives", "count": 8}
        ]

        return Response({
            "top_stats": {
                "total_candidates": total_candidates,
                "active_jobs_by_status": active_jobs,
                "interviews_upcoming_count": len(upcoming_interviews),
                "active_clients": active_clients,
            },
            "upcoming_interviews": upcoming_interviews,
            "unread_activity": unread_activity,
            "hires_by_client": hires_by_client,
            "funnel_trend": funnel_trend,
            "efficiency_metrics": efficiency_metrics,
            "top_sourcing_channels": top_sourcing_channels
        })



# ---------------------------------------------------------------------------
# Organization Email Config — GET/PUT/PATCH (admin only)
# ---------------------------------------------------------------------------

class OrganizationEmailConfigView(APIView):
    """
    Manage the SMTP email configuration for the authenticated user's organization.
    GET  /api/v1/org/email-config/       — retrieve current config
    PUT  /api/v1/org/email-config/       — full update
    PATCH /api/v1/org/email-config/      — partial update
    """
    permission_classes = [IsAdmin]

    def _get_or_create_config(self, org):
        config, _ = OrganizationEmailConfig.objects.get_or_create(organization=org)
        return config

    def get(self, request):
        config = self._get_or_create_config(request.user.organization)
        serializer = OrganizationEmailConfigSerializer(config)
        return Response(serializer.data)

    def put(self, request):
        config = self._get_or_create_config(request.user.organization)
        serializer = OrganizationEmailConfigSerializer(config, data=request.data)
        if serializer.is_valid():
            serializer.save()
            log_action(request.user, 'updated', 'OrganizationEmailConfig', config.id, 'Updated org email config')
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        config = self._get_or_create_config(request.user.organization)
        serializer = OrganizationEmailConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            log_action(request.user, 'updated', 'OrganizationEmailConfig', config.id, 'Patched org email config')
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Email Templates — full CRUD per org (admin only)
# ---------------------------------------------------------------------------

class EmailTemplateViewSet(viewsets.ModelViewSet):
    """
    CRUD for per-organization email templates (branding + optional custom HTML).
    Endpoint: /api/v1/org/email-templates/
    """
    permission_classes = [IsAdmin]
    serializer_class = EmailTemplateSerializer

    def get_queryset(self):
        return EmailTemplate.objects.filter(
            organization=self.request.user.organization
        ).order_by('template_key')

    def perform_create(self, serializer):
        template = serializer.save(organization=self.request.user.organization)
        log_action(
            self.request.user, 'created', 'EmailTemplate', template.id,
            f"Created email template '{template.template_key}'"
        )

    def perform_update(self, serializer):
        template = serializer.save()
        log_action(
            self.request.user, 'updated', 'EmailTemplate', template.id,
            f"Updated email template '{template.template_key}'"
        )

    def perform_destroy(self, instance):
        log_action(
            self.request.user, 'deleted', 'EmailTemplate', instance.id,
            f"Deleted email template '{instance.template_key}'"
        )
        instance.delete()
