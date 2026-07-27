from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError, NotFound
from django.utils import timezone
from django.db.models import Q
from candidates.models import Candidate, Application, CandidateStatus, ClientSubmission, SubmissionStatus, InterviewSchedule
from candidates.serializers import CandidateSerializer, ApplicationSerializer, InterviewScheduleSerializer, ClientSubmissionSerializer
from jobs.models import Job, Stage
from accounts.models import UserRole
from audit.utils import log_action
from candidates.tasks import simulate_client_submission_email, simulate_resume_submission_notification
from common.permissions import IsAdminOrManager, IsAdmin

class CandidateViewSet(viewsets.ModelViewSet):
    serializer_class = CandidateSerializer

    def get_permissions(self):
        """RBAC via common.permissions + role-scoped QS.
        Recruiters can list/create/parse/upload for pool + assigned.
        Destroy restricted to admin.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'parse_resume', 'upload_resume']:
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
            return qs.filter(
                Q(applications__job__assigned_recruiters=user) | Q(applications__isnull=True)
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
        except Exception as e:
            raise ValidationError({"error": f"Parse failed: {str(e)}"})


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer

    def get_permissions(self):
        """RBAC via common.permissions. All roles (incl. recruiters) can manage their assigned applications.
        Destroy restricted to admin. Uses IsAdminOrManager for safety on bulk-like actions.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'move_stage', 'schedule_interview', 'send_to_client']:
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
            return Response(ApplicationSerializer(application).data)
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
            
        return Response(ApplicationSerializer(application).data)

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
        end_date = request.query_params.get('end_date')
        
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
            interviews_qs = interviews_qs.filter(application__job__created_by=user)
            applications_qs = applications_qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            interviews_qs = interviews_qs.filter(application__job__assigned_recruiters=user)
            applications_qs = applications_qs.filter(job__assigned_recruiters=user)
            
        events_by_date = {}
        
        for interview in interviews_qs:
            date_str = interview.date.isoformat()
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append({
                "type": "interview",
                "candidate_name": interview.application.candidate.candidate_name,
                "job_title": interview.application.job.title,
                "time": str(interview.time),
                "mode": interview.mode
            })
            
        for application in applications_qs:
            if application.share_date:
                date_str = application.share_date.isoformat()
                if date_str not in events_by_date:
                    events_by_date[date_str] = []
                events_by_date[date_str].append({
                    "type": "share_date",
                    "candidate_name": application.candidate.candidate_name,
                    "job_title": application.job.title
                })
                
        response_data = [{"date": k, "events": v} for k, v in events_by_date.items()]
        return Response(response_data)

class PublicUploadView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id, is_deleted=False)
            return Response({
                "job_id": str(job.id),
                "title": job.title,
                "description": job.description,
                "company_name": job.client.company_name if job.client else "Self"
            })
        except Job.DoesNotExist:
            raise NotFound({"error": "Job not found"})

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id, is_deleted=False)
        except Job.DoesNotExist:
            raise NotFound({"error": "Job not found"})
            
        name = request.data.get('name')
        email = request.data.get('email')
        phone = request.data.get('phone')
        resume = request.FILES.get('resume')
        
        if not all([name, email, phone, resume]):
            raise ValidationError({"error": "All fields (name, email, phone, resume) are required"})
            
        # Use AI parsing for better data extraction if possible (fallback to form values)
        try:
            from .utils import parse_resume_task
            parsed = parse_resume_task(resume, organization=job.organization)
            if "error" not in parsed and not parsed.get("duplicate", False):
                name = parsed.get("candidate_name", name) or name
                email = parsed.get("email", email) or email
                phone = parsed.get("contact", phone) or phone
                current_profile = parsed.get("current_profile", "Not provided")
                current_company = parsed.get("current_company", "Not provided")
                experience = parsed.get("experience", "0 years")
                current_location = parsed.get("current_location", "Not specified")
                education = parsed.get("education", "")
                current_ctc = parsed.get("current_ctc", 0)
                expected_ctc = parsed.get("expected_ctc", 0)
            else:
                current_profile = "Not provided"
                current_company = "Not provided"
                experience = "0 years"
                current_location = "Not specified"
                education = ""
                current_ctc = 0
                expected_ctc = 0
        except Exception:
            current_profile = "Not provided"
            current_company = "Not provided"
            experience = "0 years"
            current_location = "Not specified"
            education = ""
            current_ctc = 0
            expected_ctc = 0

        candidate = Candidate.objects.create(
            candidate_name=name,
            profile_name=name,
            current_profile=current_profile,
            current_company=current_company,
            experience=experience,
            current_location=current_location,
            education=education,
            contact=phone,
            email=email,
            current_ctc=current_ctc,
            expected_ctc=expected_ctc,
            notice_period="Not specified",
            resume=resume,
            resume_file_name=resume.name,
            organization=job.organization,
            uploaded_by=None
        )
        
        first_stage = job.stages.filter(is_deleted=False).order_by('order').first()
        
        application = Application.objects.create(
            candidate=candidate,
            job=job,
            status=CandidateStatus.SCREENING.value,
            current_stage=first_stage,
            organization=job.organization
        )
        
        log_action(
            None,
            'created',
            'Candidate',
            candidate.id,
            f"Public resume upload for job '{job.title}' by {name}",
            organization=job.organization
        )
        simulate_resume_submission_notification(application.id)
        
        return Response({"message": "Resume submitted successfully! We'll be in touch."})
