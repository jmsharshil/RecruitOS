from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db.models import Q
from candidates.models import Candidate, CandidateStatus, ClientSubmission, SubmissionStatus, InterviewSchedule
from candidates.serializers import CandidateSerializer, InterviewScheduleSerializer
from jobs.models import Job, Stage
from accounts.models import UserRole
from audit.utils import log_action
from candidates.tasks import simulate_client_submission_email, simulate_resume_submission_notification

class CandidateViewSet(viewsets.ModelViewSet):
    serializer_class = CandidateSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Candidate.objects.filter(is_deleted=False)
        if user.role == UserRole.ADMIN:
            return qs
        elif user.role == UserRole.MANAGER:
            return qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            return qs.filter(job__assigned_recruiters=user)
        return Candidate.objects.none()

    def perform_create(self, serializer):
        candidate = serializer.save(created_by=self.request.user)
        log_action(self.request.user, 'created', 'Candidate', candidate.id, f"Created candidate '{candidate.candidate_name}'")

    def perform_update(self, serializer):
        candidate = serializer.save()
        log_action(self.request.user, 'updated', 'Candidate', candidate.id, f"Updated candidate '{candidate.candidate_name}'")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(self.request.user, 'deleted', 'Candidate', instance.id, f"Deleted candidate '{instance.candidate_name}'")

    @action(detail=True, methods=['post'], url_path='move-stage')
    def move_stage(self, request, pk=None):
        candidate = self.get_object()
        stage_id = request.data.get('stage_id')
        try:
            stage = Stage.objects.get(id=stage_id, job=candidate.job)
            candidate.current_stage = stage
            candidate.save()
            log_action(request.user, 'updated', 'Candidate', candidate.id, f"Stage moved to {stage.name}")
            return Response(CandidateSerializer(candidate).data)
        except Stage.DoesNotExist:
            return Response({"error": "Stage not found for this job"}, status=400)

    @action(detail=True, methods=['post'], url_path='send-to-client')
    def send_to_client(self, request, pk=None):
        candidate = self.get_object()
        if candidate.job.hiring_for != 'client':
            return Response({"error": "Job is not hiring for a client"}, status=400)
        if hasattr(candidate, 'client_submission'):
            return Response({"error": "Submission already exists"}, status=400)
            
        submission = ClientSubmission.objects.create(
            candidate=candidate,
            sent_by=request.user,
            status=SubmissionStatus.PENDING
        )
        candidate.status = CandidateStatus.SENT_TO_CLIENT
        candidate.save()
        log_action(request.user, 'sent', 'Candidate', candidate.id, f"Sent {candidate.candidate_name} to client")
        
        if candidate.job.client and candidate.job.client.email:
            simulate_client_submission_email(candidate.id, candidate.job.client.email)
            
        return Response(CandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'], url_path='schedule-interview')
    def schedule_interview(self, request, pk=None):
        candidate = self.get_object()
        serializer = InterviewScheduleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(candidate=candidate)
            candidate.status = CandidateStatus.INTERVIEW_SCHEDULED
            candidate.save()
            log_action(request.user, 'updated', 'Candidate', candidate.id, f"Scheduled interview for {candidate.candidate_name}")
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['post'], url_path='upload-resume', parser_classes=[MultiPartParser, FormParser])
    def upload_resume(self, request, pk=None):
        candidate = self.get_object()
        if 'resume' in request.FILES:
            candidate.resume = request.FILES['resume']
            candidate.resume_file_name = request.FILES['resume'].name
            candidate.save()
            return Response({"message": "Resume uploaded successfully"})
        return Response({"error": "No file provided"}, status=400)

    @action(detail=False, methods=['post'], url_path='parse-resume', parser_classes=[MultiPartParser, FormParser])
    def parse_resume(self, request):
        return Response({
            "candidate_name": "Amit Sharma",
            "current_profile": "Senior Software Engineer",
            "current_company": "Infosys",
            "experience": "5 years",
            "education": "B.Tech Computer Science",
            "college": "NIT Surat",
            "email": "amit.sharma@email.com",
            "contact": "+91 9876543210",
            "current_location": "Bengaluru",
            "skills": ["Python", "Django", "React"]
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_candidates(self, request):
        return Response({"message": "CSV export not implemented fully yet."})

class CalendarEventsView(APIView):
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            return Response({"error": "start_date and end_date are required"}, status=400)
            
        user = request.user
        
        interviews_qs = InterviewSchedule.objects.filter(date__gte=start_date, date__lte=end_date, candidate__is_deleted=False)
        candidates_qs = Candidate.objects.filter(share_date__gte=start_date, share_date__lte=end_date, is_deleted=False)
        
        if user.role == UserRole.MANAGER:
            interviews_qs = interviews_qs.filter(candidate__job__created_by=user)
            candidates_qs = candidates_qs.filter(job__created_by=user)
        elif user.role == UserRole.RECRUITER:
            interviews_qs = interviews_qs.filter(candidate__job__assigned_recruiters=user)
            candidates_qs = candidates_qs.filter(job__assigned_recruiters=user)
            
        events_by_date = {}
        
        for interview in interviews_qs:
            date_str = interview.date.isoformat()
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append({
                "type": "interview",
                "candidate_name": interview.candidate.candidate_name,
                "job_title": interview.candidate.job.title,
                "time": str(interview.time),
                "mode": interview.mode
            })
            
        for candidate in candidates_qs:
            if candidate.share_date:
                date_str = candidate.share_date.isoformat()
                if date_str not in events_by_date:
                    events_by_date[date_str] = []
                events_by_date[date_str].append({
                    "type": "share_date",
                    "candidate_name": candidate.candidate_name,
                    "job_title": candidate.job.title
                })
                
        response_data = [{"date": k, "events": v} for k, v in events_by_date.items()]
        return Response(response_data)

class PublicUploadView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
            return Response({
                "job_id": str(job.id),
                "title": job.title,
                "description": job.description,
                "company_name": job.client.company_name if job.client else "Self"
            })
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=404)

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response({"error": "Job not found"}, status=404)
            
        name = request.data.get('name')
        email = request.data.get('email')
        phone = request.data.get('phone')
        resume = request.FILES.get('resume')
        
        if not all([name, email, phone, resume]):
            return Response({"error": "All fields (name, email, phone, resume) are required"}, status=400)
            
        first_stage = job.stages.first()
            
        candidate = Candidate.objects.create(
            job=job,
            candidate_name=name,
            profile_name=name,
            email=email,
            contact=phone,
            resume=resume,
            resume_file_name=resume.name,
            status=CandidateStatus.SCREENING,
            current_stage=first_stage
        )
        
        simulate_resume_submission_notification(candidate.id)
        
        return Response({"message": "Resume submitted successfully! We'll be in touch."})
