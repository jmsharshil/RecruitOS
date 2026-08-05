from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q

from jobs.models import Job, Stage, DEFAULT_STAGES, JobStatus
from jobs.serializers import JobListSerializer, JobDetailSerializer, StageSerializer
from jobs.filters import JobFilterSet
from common.permissions import IsAdminOrManager, IsAdmin
from accounts.models import User, UserRole
from accounts.serializers import UserBriefSerializer
from audit.utils import log_action
from accounts.email_utils import send_org_email
from django.conf import settings
class JobViewSet(viewsets.ModelViewSet):
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = JobFilterSet
    search_fields    = ['title', 'description', 'location', 'code', 'status']
    ordering_fields  = ['title', 'created_at', 'target_closing_date', 'priority', 'status']
    ordering         = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        return JobDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Job.objects.filter(is_deleted=False, organization=user.organization)
        if user.role == UserRole.ADMIN:
            return qs
        elif user.role == UserRole.MANAGER:
            return qs.filter(Q(created_by=user) | Q(hiring_manager=user))
        elif user.role == UserRole.RECRUITER:
            return qs.filter(assigned_recruiters=user)
        return Job.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'upload_link']:
            return [permissions.IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        # Mutating actions restricted to admin/manager (create, update, status, stages, manage_recruiters)
        return [IsAdminOrManager()]

    def _notify_new_recruiters(self, job, new_recruiters):
        for recruiter in new_recruiters:
            try:
                frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
                url = f"{frontend_base}/jobs/{job.id}"
                context = {
                    'recruiter_name': recruiter.name,
                    'job_title': job.title,
                    'assigner_name': self.request.user.name,
                    'url': url,
                    'plain_message': f"You have been assigned to a new job: {job.title} by {self.request.user.name}.",
                }
                send_org_email(
                    organization=job.organization,
                    subject=f"New Job Assignment: {job.title}",
                    template_name='job_assigned',
                    context=context,
                    recipient_list=[recruiter.email],
                    from_email_override=self.request.user.email,
                )
            except Exception:
                pass

    def perform_create(self, serializer):
        job = serializer.save(created_by=self.request.user, organization=self.request.user.organization)
        
        # Notify if any recruiters were assigned during creation
        new_recruiters = set(job.assigned_recruiters.all())
        if new_recruiters:
            self._notify_new_recruiters(job, new_recruiters)

        log_action(self.request.user, 'created', 'Job', job.id, f"Created job '{job.title}'")

    def perform_update(self, serializer):
        job_instance = self.get_object()
        old_recruiters = set(job_instance.assigned_recruiters.all())
        
        job = serializer.save()
        
        new_recruiters = set(job.assigned_recruiters.all()) - old_recruiters
        if new_recruiters:
            self._notify_new_recruiters(job, new_recruiters)
            
        log_action(self.request.user, 'updated', 'Job', job.id, f"Updated job '{job.title}'")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(self.request.user, 'deleted', 'Job', instance.id, f"Deleted job '{instance.title}'")

    @action(detail=True, methods=['patch'], url_path='status')
    def change_status(self, request, pk=None):
        job = self.get_object()
        status_val = request.data.get('status')
        if status_val in dict(JobStatus.choices):
            job.status = status_val
            job.save()
            log_action(self.request.user, 'updated', 'Job', job.id, f"Status changed to {status_val}")
            return Response({'status': job.status})
        raise ValidationError({"error": "Invalid status"})

    @action(detail=True, methods=['post'], url_path='stages')
    def add_stage(self, request, pk=None):
        job = self.get_object()
        serializer = StageSerializer(data=request.data)
        if serializer.is_valid():
            stage = serializer.save(
                job=job,
                created_by=request.user,
                organization=job.organization
            )
            log_action(request.user, 'created', 'Stage', stage.id, f"Added stage '{stage.name}' to job '{job.title}'")
            return Response(serializer.data, status=201)
        raise ValidationError(serializer.errors)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'stages/(?P<sid>[^/.]+)')
    def manage_stage(self, request, pk=None, sid=None):
        job = self.get_object()
        try:
            stage = Stage.objects.get(id=sid, job=job, is_deleted=False)
        except Stage.DoesNotExist:
            raise NotFound({"error": "Stage not found"})

        if request.method == 'PATCH':
            serializer = StageSerializer(stage, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                log_action(request.user, 'updated', 'Stage', stage.id, f"Updated stage '{stage.name}'")
                return Response(serializer.data)
            raise ValidationError(serializer.errors)
        elif request.method == 'DELETE':
            if stage.applications.filter(is_deleted=False).exists():
                raise ValidationError({"error": "Cannot delete stage with candidates"})
            stage.is_deleted = True
            stage.deleted_at = timezone.now()
            stage.save()
            log_action(request.user, 'deleted', 'Stage', stage.id, f"Deleted stage '{stage.name}'")
            return Response(status=204)

    @action(detail=True, methods=['post'], url_path='recruiters')
    def manage_recruiters(self, request, pk=None):
        """Bulk set assigned recruiters via full list of IDs (replaces M2M entirely).
        Client always sends complete desired list:
          - Initial: {"recruiter_ids": ["uuid1", "uuid2", "uuid3"]}
          - Add more: {"recruiter_ids": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"]}
          - Unassign (e.g. remove uuid4): {"recruiter_ids": ["uuid1", "uuid2", "uuid3", "uuid5"]}
        Validates all are valid RECRUITER in same org. Uses .set() + audit logging.
        """
        job = self.get_object()
        recruiter_ids = request.data.get('recruiter_ids')

        if not isinstance(recruiter_ids, list):
            raise ValidationError({"error": "recruiter_ids must be a list"})

        # Normalize to strings (handles UUIDs from JSON)
        recruiter_ids = [str(rid).strip() for rid in recruiter_ids if rid]

        if not recruiter_ids:
            job.assigned_recruiters.clear()
            log_action(
                request.user, 'unassigned', 'Job', job.id,
                f"Unassigned all recruiters from job '{job.title}'"
            )
            return Response({"status": "updated", "assigned_recruiters": []})

        # Validate all provided IDs exist + are recruiters in org
        recruiters_qs = User.objects.filter(
            id__in=recruiter_ids,
            role=UserRole.RECRUITER,
            organization=job.organization,
            is_active=True
        ).distinct()

        found_ids = {str(r.id) for r in recruiters_qs}
        provided_set = set(recruiter_ids)
        if found_ids != provided_set:
            invalid = list(provided_set - found_ids)
            raise ValidationError({
                "error": "Some recruiter IDs are invalid, inactive, or not in organization",
                "invalid_ids": invalid
            })

        old_recruiters = set(job.assigned_recruiters.all())
        job.assigned_recruiters.set(recruiters_qs)
        new_recruiters = set(recruiters_qs) - old_recruiters
        if new_recruiters:
            self._notify_new_recruiters(job, new_recruiters)

        log_action(
            request.user, 'updated', 'Job', job.id,
            f"Set {len(recruiters_qs)} assigned recruiters on job '{job.title}' (IDs: {', '.join(str(i) for i in recruiter_ids)})"
        )

        recruiter_data = UserBriefSerializer(recruiters_qs, many=True).data
        return Response({
            "status": "updated",
            "assigned_recruiters": recruiter_data
        })

    @action(detail=True, methods=['get'], url_path='pipeline')
    def pipeline(self, request, pk=None):
        """
        Returns all applications for this job grouped by their status (stage).
        """
        job = self.get_object()
        from candidates.models import Application, CandidateStatus
        
        apps = Application.objects.filter(job=job, is_deleted=False).select_related('candidate')
        
        pipeline_data = {
            choice[0]: [] for choice in CandidateStatus.choices
        }
        
        for app in apps:
            app_data = {
                "application_id": str(app.id),
                "candidate_id": str(app.candidate.id),
                "candidate_name": app.candidate.candidate_name,
                "current_company": app.candidate.current_company,
                "experience": app.candidate.experience,
                "current_ctc": str(app.current_ctc) if app.current_ctc else "",
                "expected_ctc": str(app.expected_ctc) if app.expected_ctc else "",
                "notice_period": app.notice_period,
                "notes": app.manager_review_notes or app.feedback or app.reason_for_change,
                "status": app.status
            }
            
            if app.status in pipeline_data:
                pipeline_data[app.status].append(app_data)
            else:
                pipeline_data[app.status] = [app_data]
                
        return Response(pipeline_data)
