from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from jobs.models import Job, Stage, DEFAULT_STAGES, JobStatus
from jobs.serializers import JobSerializer, StageSerializer
from common.permissions import IsAdminOrManager, IsAdmin, IsManager
from accounts.models import UserRole
from audit.utils import log_action

class JobViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrManager]
    serializer_class = JobSerializer

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
        if self.action == 'destroy':
            return [IsAdmin()]
        return super().get_permissions()

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
        return Response({"error": "Invalid status"}, status=400)

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
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'stages/(?P<sid>[^/.]+)')
    def manage_stage(self, request, pk=None, sid=None):
        job = self.get_object()
        try:
            stage = Stage.objects.get(id=sid, job=job, is_deleted=False)
        except Stage.DoesNotExist:
            return Response(status=404)

        if request.method == 'PATCH':
            serializer = StageSerializer(stage, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                log_action(request.user, 'updated', 'Stage', stage.id, f"Updated stage '{stage.name}'")
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        elif request.method == 'DELETE':
            if stage.applications.filter(is_deleted=False).exists():
                return Response({"error": "Cannot delete stage with candidates"}, status=400)
            stage.is_deleted = True
            stage.deleted_at = timezone.now()
            stage.save()
            log_action(request.user, 'deleted', 'Stage', stage.id, f"Deleted stage '{stage.name}'")
            return Response(status=204)

    @action(detail=True, methods=['get'], url_path='upload-link')
    def get_upload_link(self, request, pk=None):
        job = self.get_object()
        return Response({"resume_upload_link": job.resume_upload_link})
