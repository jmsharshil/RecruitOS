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
import logging
from common.task_queue import TASK_QUEUE

from django.conf import settings
from accounts.email_utils import send_org_email
from candidates.models import (
    Candidate, Application, CandidateStatus,
    ClientSubmission, SubmissionStatus, InterviewSchedule,
    ManagerReviewStatus, ApplicationHistory,
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

logger = logging.getLogger(__name__)

class CandidateViewSet(viewsets.ModelViewSet):
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = CandidateFilterSet
    search_fields    = [
        'candidate_name', 'email', 'contact', 'current_profile', 
        'current_company', 'current_location', 'education', 
        'skills', 'tags'
    ]
    ordering_fields  = ['candidate_name', 'created_at', 'experience']
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
                Q(applications__job__created_by=user) | Q(applications__job__hiring_manager=user) | Q(applications__isnull=True)
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
        # Notifications are now handled by the background parsing task or bulk upload view
        # after candidate details are actually populated.

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
        """Upload resume to existing candidate. Parsing now runs in background via TASK_QUEUE
        (from common.task_queue) to avoid blocking the API call. Candidate is saved immediately
        with the file; AI enrichment happens asynchronously and updates only empty fields.
        Supports 'multiple upload' pattern by queuing independent parse tasks per file.
        """
        candidate = self.get_object()
        if 'resume' not in request.FILES:
            raise ValidationError({"error": "No file provided"})

        resume_file = request.FILES['resume']
        parsed_data = {}
        updated = False
        successful_parse = False

        try:
            from .utils import parse_resume_task
            parsed = parse_resume_task(
                resume_file, organization=request.user.organization
            )
            if isinstance(parsed, dict) and "error" not in parsed:
                parsed_data = parsed
                successful_parse = True
                # Update only fields that are empty or have placeholder values.
                mapping = {
                    'candidate_name': 'candidate_name',
                    'profile_name': 'profile_name',
                    'current_profile': 'current_profile',
                    'current_company': 'current_company',
                    'experience': 'experience',
                    'current_location': 'current_location',
                    'education': 'education',
                    'contact': 'contact',
                    'email': 'email',
                    'skills': 'skills',
                }
                for pkey, mkey in mapping.items():
                    value = parsed.get(pkey)
                    if value not in (None, '', [], {}, "Not provided", "Not specified", "0 years", 0, 0.0):
                        current_val = getattr(candidate, mkey, None)
                        if not current_val or str(current_val).strip() in ('', 'Not provided', 'Not specified', '0 years'):
                            if mkey == 'skills' and isinstance(value, list):
                                if not getattr(candidate, 'skills') or len(getattr(candidate, 'skills', [])) == 0:
                                    setattr(candidate, mkey, value)
                            else:
                                setattr(candidate, mkey, value)
                            updated = True
        except Exception as e:
            # Silent fallback - still upload the file
            parsed_data = {"parse_error": str(e)}

        # Rewind file pointer (parse_resume_task may have read it)
        try:
            resume_file.seek(0)
        except (AttributeError, OSError):
            pass

        candidate.resume = resume_file
        candidate.resume_file_name = resume_file.name
        candidate.save()

        # Enqueue background parsing using task queue threading
        from .utils import background_parse_resume
        TASK_QUEUE.enqueue(
            background_parse_resume,
            request.user,
            str(candidate.id),
            str(request.user.organization.id)
        )
        logger.info(f"[TASK] Enqueued background parse for candidate {candidate.id} ({candidate.candidate_name})")

        log_action(
            self.request.user,
            'updated',
            'Candidate',
            candidate.id,
            f"Uploaded resume for '{candidate.candidate_name}' (background parsing queued)"
        )

        response_data = {
            "message": "Resume uploaded successfully. AI parsing queued in background.",
            "resume_file_name": candidate.resume_file_name,
            "ai_parsed": False,
            "background_parsing": True,
        }
        return Response(response_data)

    @action(detail=False, methods=['post'], url_path='parse-resume', parser_classes=[MultiPartParser, FormParser])
    def parse_resume(self, request):
        """Parse resume by creating a basic Candidate record immediately then enqueuing
        background_parse_resume via TASK_QUEUE (fire-and-forget). Returns acceptance
        immediately with candidate_id + background_parsing flag. AI enrichment, duplicate
        detection, and field updates happen asynchronously. Prevents blocking OpenAI calls
        on the API thread.
        """
        if 'resume' not in request.FILES:
            raise ValidationError({"error": "No resume file provided"})

        resume_file = request.FILES['resume']
        user = self.request.user
        organization = user.organization

        # Create basic candidate synchronously (resume saved immediately)
        candidate = Candidate.objects.create(
            candidate_name="Pending AI Parse",
            profile_name="Pending AI Parse",
            current_profile="Not provided",
            current_company="Not provided",
            experience="0 years",
            current_location="Not specified",
            education=[],
            contact="",
            email="",
            skills=[],
            resume=resume_file,
            resume_file_name=resume_file.name,
            organization=organization,
            uploaded_by=user,
        )

        # Enqueue background parsing + enrichment + org-scoped duplicate check
        from .utils import background_parse_resume
        TASK_QUEUE.enqueue(
            background_parse_resume,
            str(candidate.id),
            str(organization.id)
        )
        logger.info(f"[TASK] Enqueued background parse for new candidate {candidate.id} via parse-resume endpoint")

        log_action(
            user,
            'created',
            'Candidate',
            candidate.id,
            f"Created candidate via parse-resume (background parsing queued)"
        )
        # Email notification happens asynchronously in candidates.utils.background_parse_resume

        response_data = {
            "message": "Resume parsed and candidate created. AI enrichment queued in background.",
            "candidate_id": str(candidate.id),
            "resume_file_name": candidate.resume_file_name,
            "ai_parsed": False,
            "background_parsing": True,
        }
        return Response(response_data, status=201)

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
            return qs.filter(Q(job__created_by=user) | Q(job__hiring_manager=user))
        elif user.role == UserRole.RECRUITER:
            return qs.filter(job__assigned_recruiters=user)
        return qs.none()

    def perform_create(self, serializer):
        application = serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user
        )
        log_action(
            self.request.user,
            'created',
            'Application',
            application.id,
            f"Assigned candidate '{application.candidate.candidate_name}' to job '{application.job.title}'"
        )
        
        # Save submission to history
        ApplicationHistory.objects.create(
            application=application,
            user=self.request.user,
            action="submitted",
            notes=f"Assigned candidate to job '{application.job.title}'",
            organization=application.organization
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
            
            # Save stage moved to history
            ApplicationHistory.objects.create(
                application=application,
                user=request.user,
                action="stage_moved",
                notes=f"Moved candidate to stage '{stage.name}'",
                organization=application.organization
            )

            return Response(ApplicationDetailSerializer(application).data)
        except Stage.DoesNotExist:
            raise ValidationError({"error": "Invalid stage for this job", "detail": "Stage not found for this job"})

    @action(detail=True, methods=['post'], url_path='send-to-client')
    def send_to_client(self, request, pk=None):
        application = self.get_object()
        if application.job.hiring_for != 'client':
            raise ValidationError({"error": "Job is not hiring for a client"})

        # Prevent sharing the same candidate for the same job to the same client within 3 months (90 days)
        if request.user.role == 'recruiter':
            from django.utils import timezone
            from datetime import timedelta
            three_months_ago = timezone.now() - timedelta(days=90)
            
            duplicate_client_sub = ClientSubmission.objects.filter(
                application__candidate=application.candidate,
                application__job__client=application.job.client,
                sent_at__gte=three_months_ago
            )
            if duplicate_client_sub.exists():
                raise ValidationError({
                    "error": "You have already shared/submitted this candidate profile to this client in the last 3 months."
                })

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

        # Save send to client to history
        client_name = application.job.client.company_name if application.job.client else "client"
        ApplicationHistory.objects.create(
            application=application,
            user=request.user,
            action="sent_to_client",
            notes=f"Shared candidate profile with client: {client_name}",
            organization=application.organization
        )

        if application.job.client:
            client_email = application.job.client.email
            recipient_name = application.job.client.company_name
            if application.job.team_member_id and isinstance(application.job.client.team_members, list):
                for tm in application.job.client.team_members:
                    if isinstance(tm, dict) and str(tm.get('id')) == str(application.job.team_member_id) and tm.get('email'):
                        client_email = tm.get('email')
                        recipient_name = tm.get('name', recipient_name)
                        break
            
            if client_email:
                simulate_client_submission_email(application.id, client_email, recipient_name)

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
            
            # Save interview scheduled to history
            ApplicationHistory.objects.create(
                application=application,
                user=request.user,
                action="interview_scheduled",
                notes=f"Scheduled {schedule.mode} interview on {schedule.date} at {schedule.time}",
                organization=application.organization
            )

            return Response(InterviewScheduleSerializer(schedule).data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        application = self.get_object()
        status = request.data.get('status')
        notes = request.data.get('notes', '')

        if status not in ManagerReviewStatus.values:
            raise ValidationError({
                "error": "Invalid review status",
                "detail": f"Status must be one of: {ManagerReviewStatus.values}"
            })

        # Save review details
        application.manager_review_status = status
        application.manager_review_notes = notes

        # Map rejection to overall application status
        if status == ManagerReviewStatus.REJECTED:
            application.status = CandidateStatus.REJECTED.value

        application.save()
        log_action(
            request.user, 'reviewed', 'Application', application.id,
            f"Manager review action: {status} with notes: '{notes[:60]}'"
        )

        # Save manager review action to history
        ApplicationHistory.objects.create(
            application=application,
            user=request.user,
            action=status,
            notes=notes,
            organization=application.organization
        )

        # Trigger email notification to recruiter
        try:
            send_manager_review_email(application)
        except Exception as e:
            print(f"Failed to send manager review email: {e}")

        return Response(ApplicationDetailSerializer(application).data)


def send_manager_review_email(application):
    recruiter = application.created_by or application.candidate.uploaded_by
    if not recruiter:
        print("No recruiter associated with application. Skipping email.")
        return

    manager = application.job.hiring_manager or application.job.created_by
    manager_name = manager.name if manager else "A Manager"
    manager_email = manager.email if manager else ""

    frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')
    url = f"{frontend_base}/candidates/{application.candidate.id}"

    context = {
        "recruiter": recruiter,
        "candidate": application.candidate,
        "job": application.job,
        "manager_name": manager_name,
        "manager_email": manager_email,
        "status": application.manager_review_status,
        "notes": application.manager_review_notes,
        "url": url,
        "org_name": application.organization.name if application.organization else "RecruitOS"
    }

    send_org_email(
        organization=application.organization,
        subject=f"Candidate Review: {application.candidate.candidate_name} — {application.manager_review_status.upper()}",
        template_name="manager_review",
        context=context,
        recipient_list=[recruiter.email]
    )


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

from accounts.models import Organization

class TalentPoolPublicUploadView(APIView):
    """
    Public (AllowAny) endpoint for talent pool resume submissions.
    Supports ?org_id=... query param (or in POST data) for unauthenticated submissions.
    Creates Candidate record synchronously with form/resume data; enqueues
    background_parse_resume via TASK_QUEUE for AI enrichment + org-scoped duplicate
    detection. No blocking OpenAI calls on request thread. Returns immediately with
    background_parsing=True. Matches updated Candidate model (no per-job CTC/notice).
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def get(self, request):
        """Optional GET to return public upload info or validate org (e.g. from job link).
        Updated to support AllowAny + org_id query param for true public talent pool submissions.
        """
        org_id = request.query_params.get('org_id')
        if org_id:
            try:
                org = Organization.objects.get(id=org_id)
                return Response({"organization": {"id": str(org.id), "name": org.name}})
            except Organization.DoesNotExist:
                return Response({"error": "Organization not found"}, status=404)
        user = request.user
        if user.is_authenticated:
            try:
                org = Organization.objects.get(id=user.organization.id)
                return Response({"organization": {"id": str(org.id), "name": org.name}})
            except Organization.DoesNotExist:
                pass
        return Response({
            "message": "POST name, email, phone, resume, org_id to submit to talent pool.",
            "note": "org_id query param or authenticated user required for scoping."
        })

    def post(self, request):
        resumes = request.FILES.getlist('resume')
        if not resumes:
            raise ValidationError({"error": "No resume files provided. Use the 'resume' key."})

        user = request.user
        from accounts.models import Organization
        try:
            organization = Organization.objects.get(id=user.organization.id)
        except Organization.DoesNotExist:
            raise ValidationError({"error": "Organization not found"})

        results = []
        successful_count = 0
        failed_count = 0

        for resume in resumes:
            ai_parsed = False
            parsed_data = {}
            # For single uploads, respect form data overrides. For batch, ignore them.
            if len(resumes) == 1:
                name = request.data.get("name") or request.data.get("candidate_name", "Unnamed Candidate")
                email = (request.data.get("email", "") or "").strip().lower()
                phone = request.data.get("phone") or request.data.get("contact", "")
                current_profile = request.data.get("current_profile", None)
                current_company = request.data.get("current_company", None)
                experience = request.data.get("experience", None)
                current_location = request.data.get("current_location", None)
                education = request.data.get("education", [])
                skills = request.data.get("skills", [])
            else:
                name, email, phone = "Unnamed Candidate", "", ""
                current_profile, current_company, experience, current_location = None, None, None, None
                education, skills = [], []

            try:
                from .utils import parse_resume_task
                parsed = parse_resume_task(resume, organization=organization)
                if isinstance(parsed, dict) and "error" not in parsed:
                    ai_parsed = True
                    parsed_data = parsed
                    name = parsed.get("candidate_name") or parsed.get("name") or parsed.get("profile_name") or name
                    email = (parsed.get("email") or email or "").strip().lower()
                    phone = parsed.get("contact") or parsed.get("phone_number") or parsed.get("phone") or phone
                    current_profile = parsed.get("current_profile") or parsed.get("title") or current_profile
                    current_company = parsed.get("current_company") or parsed.get("current_employer") or current_company
                    experience = parsed.get("experience") or experience
                    current_location = parsed.get("current_location") or parsed.get("location") or current_location
                    if isinstance(parsed.get("education"), (list, dict)):
                        education = parsed.get("education")
                    skills = parsed.get("skills") or skills
            except Exception as e:
                parsed_data = {"parse_error": str(e)}

            # If name wasn't found or parsing failed, fallback to the filename (without extension)
            if name == "Unnamed Candidate" or not name.strip():
                from pathlib import Path
                name = Path(getattr(resume, "name", "Unnamed Candidate")).stem

            # Rewind file pointer
            try:
                resume.seek(0)
            except (AttributeError, OSError):
                pass

            # Normalize for JSONFields in model
            if not isinstance(skills, list):
                skills = [s.strip() for s in str(skills).split(",") if s.strip()] if skills else []
            if not isinstance(education, (list, dict)):
                education = [education] if education and str(education).strip() else []

            # Duplicate handling
            is_duplicate = parsed_data.get("duplicate", False)
            duplicate_of = None
            if parsed_data.get("existing_candidate_id"):
                try:
                    duplicate_of = Candidate.objects.get(
                        id=parsed_data.get("existing_candidate_id"),
                        organization=organization,
                        is_deleted=False
                    )
                except (Candidate.DoesNotExist, ValueError, TypeError):
                    pass
            elif email:
                old_candidate = Candidate.objects.filter(
                    email__iexact=email,
                    organization=organization,
                    is_deleted=False
                ).first()
                if old_candidate:
                    is_duplicate = True
                    duplicate_of = old_candidate

            try:
                # Create candidate
                candidate = Candidate.objects.create(
                    candidate_name=name,
                    profile_name=name,
                    current_profile=current_profile or "Not specified",
                    current_company=current_company or "Not specified",
                    experience=experience or "Not specified",
                    current_location=current_location or "Not specified",
                    education=education,
                    contact=phone,
                    email=email,
                    skills=skills,
                    resume=resume,
                    resume_file_name=getattr(resume, "name", "resume.pdf"),
                    organization=organization,
                    uploaded_by=user if user.is_authenticated else None,
                    is_duplicate=is_duplicate,
                    duplicate_of=duplicate_of,
                )

                log_action(
                    user,
                    'created',
                    'Candidate',
                    candidate.id,
                    f"Resume upload by {name} {'(AI-parsed)' if ai_parsed else '(form)'}",
                    organization=organization
                )
                simulate_resume_submission_notification(candidate.id)

                result_item = {
                    "filename": getattr(resume, "name", "resume.pdf"),
                    "status": "success",
                    "candidate_id": str(candidate.id),
                    "ai_parsed": ai_parsed,
                    "candidate": CandidateDetailSerializer(candidate).data,
                }
                if is_duplicate or parsed_data.get("duplicate"):
                    result_item["note"] = parsed_data.get("message", "Duplicate detected in pool")
                
                results.append(result_item)
                successful_count += 1
            except Exception as e:
                results.append({
                    "filename": getattr(resume, "name", "resume.pdf"),
                    "status": "failed",
                    "error": str(e)
                })
                failed_count += 1

        # Response logic
        any_unparsed = failed_count > 0 or any(not r.get("ai_parsed", False) for r in results if r["status"] == "success")
        
        if any_unparsed:
            final_msg = "Resume is not parsed. Please edit manually in candidate list"
        else:
            final_msg = "Resume submitted successfully! please check in candidate list"

        response_data = {
            "message": final_msg,
            "total_processed": len(resumes),
            "successful": successful_count,
            "failed": failed_count,
            "results": results
        }
        return Response(response_data, status=201)