from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from jobs.models import Job, Stage, DEFAULT_STAGES, JobStatus
from jobs.serializers import JobListSerializer, JobDetailSerializer, StageSerializer
from jobs.filters import JobFilterSet
from common.permissions import IsAdminOrManager, IsAdmin
from accounts.models import User, UserRole
from accounts.serializers import UserBriefSerializer
from audit.utils import log_action

class JobViewSet(viewsets.ModelViewSet):
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = JobFilterSet
    search_fields    = ['title', 'description', 'location', 'code']
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
            return qs.filter(created_by=user)
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

    def perform_create(self, serializer):
        job = serializer.save(created_by=self.request.user, organization=self.request.user.organization)

        # Auto-create default stages
        for stage_data in DEFAULT_STAGES:
            Stage.objects.create(
                job=job,
                created_by=self.request.user,
                organization=job.organization,
                **stage_data
            )

        log_action(self.request.user, 'created', 'Job', job.id, f"Created job '{job.title}'")

    def perform_update(self, serializer):
        job = serializer.save()
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

        job.assigned_recruiters.set(recruiters_qs)
        log_action(
            request.user, 'updated', 'Job', job.id,
            f"Set {len(recruiters_qs)} assigned recruiters on job '{job.title}' (IDs: {', '.join(str(i) for i in recruiter_ids)})"
        )

        recruiter_data = UserBriefSerializer(recruiters_qs, many=True).data
        return Response({
            "status": "updated",
            "assigned_recruiters": recruiter_data
        })
