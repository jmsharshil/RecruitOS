from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q

from candidates.models import (
    Candidate, Application, CandidateStatus,
    ClientSubmission, SubmissionStatus, InterviewSchedule,
)
from candidates.serializers import (
    CandidateListSerializer, CandidateDetailSerializer,
    ApplicationListSerializer, ApplicationDetailSerializer,
    InterviewScheduleSerializer, ClientSubmissionSerializer,
)
from candidates.filters import CandidateFilterSet, ApplicationFilterSet
from jobs.models import Job, Stage
from accounts.models import UserRole
from audit.utils import log_action
from candidates.tasks import simulate_client_submission_email, simulate_resume_submission_notification
from common.permissions import IsAdminOrManager, IsAdmin

class CandidateViewSet(viewsets.ModelViewSet):
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = CandidateFilterSet
    search_fields    = ['candidate_name', 'email', 'contact', 'current_profile', 'current_company', 'current_location']
    ordering_fields  = ['candidate_name', 'created_at', 'current_ctc', 'expected_ctc', 'experience']
    ordering         = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return CandidateListSerializer
        return CandidateDetailSerializer

    def get_permissions(self):
        """
        RBAC via common.permissions + role-scoped QS (updated for recruiter visibility).
        Recruiters can list/create/parse/upload for full pool + their assigned-job candidates.
        Destroy restricted to admin only.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update',
                           'parse_resume', 'upload_resume', 'mark_duplicate', 'unmark_duplicate']:
            return [permissions.IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        user = self.request.user
        qs = Candidate.objects.filter(
            is_deleted=False,
            organization=user.organization
        )
        if user.role == UserRole.ADMIN:
            return qs
        elif user.role == UserRole.MANAGER:
            return qs.filter(
                Q(applications__job__created_by=user) | Q(applications__isnull=True)
            ).distinct()
        elif user.role == UserRole.RECRUITER:
            # Recruiters see full org talent pool + candidates linked to their assigned jobs
            # (consistent with ApplicationViewSet and export)
            return qs.filter(
                Q(applications__isnull=True) |
                Q(applications__job__assigned_recruiters=user)
            ).distinct()
        return qs.none()

    def perform_create(self, serializer):
        candidate = serializer.save(
            uploaded_by=self.request.user,
            organization=self.request.user.organization
        )
        log_action(self.request.user, 'created', 'Candidate', candidate.id, f"Created candidate '{candidate.candidate_name}'")
        # Notify recruiters for pure pool candidates
        simulate_resume_submission_notification(candidate.id)

    def perform_update(self, serializer):
        candidate = serializer.save()
        log_action(self.request.user, 'updated', 'Candidate', candidate.id, f"Updated candidate '{candidate.candidate_name}'")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(self.request.user, 'deleted', 'Candidate', instance.id, f"Deleted candidate '{instance.candidate_name}'")

    @action(detail=True, methods=['post'], url_path='upload-resume', parser_classes=[MultiPartParser, FormParser])
    def upload_resume(self, request, pk=None):
        candidate = self.get_object()
        if 'resume' in request.FILES:
            candidate.resume = request.FILES['resume']
            candidate.resume_file_name = request.FILES['resume'].name
            candidate.save()
            return Response({"message": "Resume uploaded successfully"})
        raise ValidationError({"error": "No file provided"})

    @action(detail=False, methods=['post'], url_path='parse-resume', parser_classes=[MultiPartParser, FormParser])
    def parse_resume(self, request):
        if 'resume' not in request.FILES:
            raise ValidationError({"error": "No resume file provided"})
        try:
            from .utils import parse_resume_task
            # Pass organization for scoped duplicate detection in shared talent pool
            parsed_data = parse_resume_task(
                request.FILES['resume'],
                organization=request.user.organization
            )
            if isinstance(parsed_data, dict) and "error" in parsed_data:
                raise ValidationError(parsed_data)
            return Response(parsed_data)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError({"error": f"Parse failed: {str(e)}"})

    @action(detail=True, methods=['post'], url_path='mark-duplicate')
    def mark_duplicate(self, request, pk=None):
        """
        Mark this candidate as a duplicate of another.
        POST body: { "duplicate_of": "<candidate_uuid>" }
        """
        candidate = self.get_object()
        dup_of_id = request.data.get('duplicate_of')
        if not dup_of_id:
            raise ValidationError({"error": "'duplicate_of' candidate ID is required."})
        try:
            canonical = Candidate.objects.get(
                id=dup_of_id,
                organization=request.user.organization,
                is_deleted=False
            )
        except Candidate.DoesNotExist:
            raise ValidationError({"error": "Canonical candidate not found."})
        if canonical.pk == candidate.pk:
            raise ValidationError({"error": "A candidate cannot be a duplicate of itself."})

        candidate.is_duplicate = True
        candidate.duplicate_of = canonical
        candidate.save(update_fields=['is_duplicate', 'duplicate_of', 'updated_at'])
        log_action(
            request.user, 'updated', 'Candidate', candidate.id,
            f"Marked '{candidate.candidate_name}' as duplicate of '{canonical.candidate_name}'"
        )
        return Response({
            "message": f"Candidate marked as duplicate of '{canonical.candidate_name}'.",
            "candidate": CandidateDetailSerializer(candidate).data,
        })

    @action(detail=True, methods=['post'], url_path='unmark-duplicate')
    def unmark_duplicate(self, request, pk=None):
        """Remove the duplicate flag from this candidate."""
        candidate = self.get_object()
        candidate.is_duplicate = False
        candidate.duplicate_of = None
        candidate.save(update_fields=['is_duplicate', 'duplicate_of', 'updated_at'])
        log_action(
            request.user, 'updated', 'Candidate', candidate.id,
            f"Removed duplicate flag from '{candidate.candidate_name}'"
        )
        return Response({"message": "Duplicate flag removed.", "candidate": CandidateDetailSerializer(candidate).data})


class ApplicationViewSet(viewsets.ModelViewSet):
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = ApplicationFilterSet
    search_fields    = ['candidate__candidate_name', 'candidate__email', 'job__title']
    ordering_fields  = ['created_at', 'share_date', 'status']
    ordering         = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ApplicationListSerializer
        return ApplicationDetailSerializer

    def get_permissions(self):
        """
        RBAC via common.permissions. All roles (incl. recruiters) can manage their assigned applications.
        Destroy restricted to admin. Uses IsAdminOrManager for safety on bulk-like actions.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update',
                           'move_stage', 'schedule_interview', 'send_to_client']:
            return [permissions.IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        return [IsAdminOrManager()]

    def get_queryset(self):
        user = self.request.user
        qs = Application.objects.filter(is_deleted=False, organization=user.organization)
        if user.role == UserRole.ADMIN:
            return qs
        elif user.role == UserRole.MANAGER:
            return qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            return qs.filter(job__assigned_recruiters=user)
        return qs.none()

    def perform_create(self, serializer):
        application = serializer.save(organization=self.request.user.organization)
        log_action(
            self.request.user,
            'created',
            'Application',
            application.id,
            f"Assigned candidate '{application.candidate.candidate_name}' to job '{application.job.title}'"
        )
        if not application.current_stage:
            first_stage = application.job.stages.filter(
                is_deleted=False
            ).order_by('order').first()
            if first_stage:
                application.current_stage = first_stage
                application.save()

    def perform_update(self, serializer):
        application = serializer.save()
        log_action(self.request.user, 'updated', 'Application', application.id, f"Updated application for {application.candidate.candidate_name}")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(self.request.user, 'deleted', 'Application', instance.id, f"Deleted application for {instance.candidate.candidate_name}")

    @action(detail=True, methods=['post'], url_path='move-stage')
    def move_stage(self, request, pk=None):
        application = self.get_object()
        stage_id = request.data.get('stage_id')
        try:
            stage = Stage.objects.get(id=stage_id, job=application.job)
            application.current_stage = stage
            if stage.name.lower() == "hired":
                application.status = CandidateStatus.HIRED.value
            application.save()
            log_action(request.user, 'updated', 'Application', application.id, f"Stage moved to {stage.name}")
            return Response(ApplicationDetailSerializer(application).data)
        except Stage.DoesNotExist:
            raise ValidationError({"error": "Invalid stage for this job", "detail": "Stage not found for this job"})

    @action(detail=True, methods=['post'], url_path='send-to-client')
    def send_to_client(self, request, pk=None):
        application = self.get_object()
        if application.job.hiring_for != 'client':
            raise ValidationError({"error": "Job is not hiring for a client"})
        if hasattr(application, 'client_submission'):
            raise ValidationError({"error": "Submission already exists"})

        submission = ClientSubmission.objects.create(
            application=application,
            sent_by=request.user,
            status=SubmissionStatus.PENDING,
            organization=request.user.organization
        )
        application.status = CandidateStatus.SENT_TO_CLIENT.value
        application.save()
        log_action(request.user, 'sent', 'Application', application.id, f"Sent {application.candidate.candidate_name} to client")

        if application.job.client and application.job.client.email:
            simulate_client_submission_email(application.id, application.job.client.email)

        return Response(ApplicationDetailSerializer(application).data)

    @action(detail=True, methods=['post'], url_path='schedule-interview')
    def schedule_interview(self, request, pk=None):
        application = self.get_object()
        serializer = InterviewScheduleSerializer(data=request.data)
        if serializer.is_valid():
            schedule = serializer.save(
                application=application,
                organization=request.user.organization
            )
            application.status = CandidateStatus.INTERVIEW_SCHEDULED.value
            application.save()
            log_action(request.user, 'updated', 'Application', application.id, f"Scheduled interview for {application.candidate.candidate_name}")
            return Response(InterviewScheduleSerializer(schedule).data, status=201)
        return Response(serializer.errors, status=400)


class CalendarEventsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date   = request.query_params.get('end_date')

        if not start_date or not end_date:
            raise ValidationError({"error": "start_date and end_date are required"})

        user = request.user

        interviews_qs = InterviewSchedule.objects.filter(
            is_deleted=False,
            date__gte=start_date,
            date__lte=end_date,
            application__is_deleted=False,
            application__candidate__is_deleted=False,
            organization=user.organization
        )
        applications_qs = Application.objects.filter(
            share_date__gte=start_date,
            share_date__lte=end_date,
            is_deleted=False,
            organization=user.organization
        )

        if user.role == UserRole.MANAGER:
            interviews_qs   = interviews_qs.filter(application__job__created_by=user)
            applications_qs = applications_qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            interviews_qs   = interviews_qs.filter(application__job__assigned_recruiters=user)
            applications_qs = applications_qs.filter(job__assigned_recruiters=user)

        events_by_date = {}

        for interview in interviews_qs:
            date_str = interview.date.isoformat()
            events_by_date.setdefault(date_str, []).append({
                "type": "interview",
                "candidate_name": interview.application.candidate.candidate_name,
                "job_title": interview.application.job.title,
                "time": str(interview.time),
                "mode": interview.mode
            })

        for application in applications_qs:
            if application.share_date:
                date_str = application.share_date.isoformat()
                events_by_date.setdefault(date_str, []).append({
                    "type": "share_date",
                    "candidate_name": application.candidate.candidate_name,
                    "job_title": application.job.title
                })

        response_data = [{"date": k, "events": v} for k, v in events_by_date.items()]
        return Response(response_data)


class TalentPoolPublicUploadView(APIView):
    """
    Public endpoint (AllowAny) for talent pool resume submissions.
    Requires org_id (query or form) for multi-tenant scoping. Creates pure
    Candidate (pool entry, uploaded_by=None). No auto-Application.
    Uses hardened AI parser + duplicate guard. Returns candidate_id on success.
    """
    permission_classes = [permissions.AllowAny]
    parser_classes     = [MultiPartParser, FormParser]

    def get(self, request):
        """Optional GET to return public upload info or validate org (e.g. from job link)."""
        org_id = request.query_params.get('org_id')
        if org_id:
            from accounts.models import Organization
            try:
                org = Organization.objects.get(id=org_id)
                return Response({"organization": {"id": str(org.id), "name": org.name}})
            except Organization.DoesNotExist:
                return Response({"error": "Organization not found"}, status=404)
        return Response({
            "message": "POST name, email, phone, resume, org_id to submit to talent pool.",
            "note": "org_id is now required for scoping."
        })

    def post(self, request):
        name   = request.data.get('name')
        email  = request.data.get('email')
        phone  = request.data.get('phone')
        resume = request.FILES.get('resume')
        org_id = request.query_params.get('org_id') or request.data.get('org_id')

        if not all([name, email, phone, resume, org_id]):
            raise ValidationError({
                "error": "All fields (name, email, phone, resume, org_id) are required"
            })

        from accounts.models import Organization
        try:
            organization = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise ValidationError({"error": "Organization not found"})

        # Use AI parsing for better data extraction if possible (fallback to form values)
        try:
            from .utils import parse_resume_task
            parsed = parse_resume_task(resume, organization=organization)
            if "error" not in parsed and not parsed.get("duplicate", False):
                name             = parsed.get("candidate_name", name) or name
                email            = parsed.get("email", email) or email
                phone            = parsed.get("contact", phone) or phone
                current_profile  = parsed.get("current_profile", "Not provided")
                current_company  = parsed.get("current_company", "Not provided")
                experience       = parsed.get("experience", "0 years")
                current_location = parsed.get("current_location", "Not specified")
                education        = parsed.get("education", "")
                current_ctc      = parsed.get("current_ctc", 0)
                expected_ctc     = parsed.get("expected_ctc", 0)
                skills           = parsed.get("skills", [])
            elif parsed.get("duplicate", False):
                return Response({
                    "message": "A candidate with this profile already exists in our talent pool.",
                    "duplicate": True,
                    "existing_candidate_id": parsed.get("existing_candidate_id"),
                }, status=200)
            else:
                current_profile  = "Not provided"
                current_company  = "Not provided"
                experience       = "0 years"
                current_location = "Not specified"
                education        = ""
                current_ctc      = 0
                expected_ctc     = 0
                skills           = []
        except Exception:
            current_profile  = "Not provided"
            current_company  = "Not provided"
            experience       = "0 years"
            current_location = "Not specified"
            education        = ""
            current_ctc      = 0
            expected_ctc     = 0
            skills           = []

        # Rewind file pointer after parse_resume_task read it
        try:
            resume.seek(0)
        except Exception:
            pass

        candidate = Candidate.objects.create(
            candidate_name   = name,
            profile_name     = name,
            current_profile  = current_profile,
            current_company  = current_company,
            experience       = experience,
            current_location = current_location,
            education        = education,
            contact          = phone,
            email            = email,
            current_ctc      = current_ctc,
            expected_ctc     = expected_ctc,
            notice_period    = "Not specified",
            skills           = skills,
            resume           = resume,
            resume_file_name = resume.name,
            organization     = organization,
            uploaded_by      = None
        )

        log_action(
            None, 'created', 'Candidate', candidate.id,
            f"Public talent pool upload by {name}",
            organization=organization
        )
        simulate_resume_submission_notification(candidate.id)

        return Response({
            "message": "Resume submitted successfully! We'll be in touch.",
            "candidate_id": str(candidate.id)
        }, status=201)