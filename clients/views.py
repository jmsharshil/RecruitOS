from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from clients.models import Client, POC, ClientDocument
from clients.serializers import ClientSerializer, POCSerializer, ClientDocumentSerializer
from common.permissions import IsAdminOrManager, IsAdmin
from accounts.models import UserRole
from audit.utils import log_action

class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrManager]
    serializer_class = ClientSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Client.objects.filter(is_deleted=False, organization=user.organization)
        if user.role == UserRole.ADMIN or user.role == UserRole.MANAGER:
            return qs
        elif user.role == UserRole.RECRUITER:
            return qs.filter(
                jobs__is_deleted=False, 
                jobs__assigned_recruiters=user
            ).distinct()
        return Client.objects.none()

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        client = serializer.save(created_by=self.request.user, organization=self.request.user.organization)
        log_action(self.request.user, 'created', 'Client', client.id, f"Created client '{client.company_name}'")

    def perform_update(self, serializer):
        client = serializer.save()
        log_action(self.request.user, 'updated', 'Client', client.id, f"Updated client '{client.company_name}'")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        log_action(self.request.user, 'deleted', 'Client', instance.id, f"Deleted client '{instance.company_name}'")

    @action(detail=True, methods=['post'], url_path='pocs')
    def add_poc(self, request, pk=None):
        client = self.get_object()
        serializer = POCSerializer(data=request.data)
        if serializer.is_valid():
            poc = serializer.save(client=client, organization=client.organization)
            log_action(self.request.user, 'created', 'POC', poc.id, f"Added POC for client '{client.company_name}'")
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'pocs/(?P<poc_id>[^/.]+)')
    def manage_poc(self, request, pk=None, poc_id=None):
        client = self.get_object()
        try:
            poc = POC.objects.get(id=poc_id, client=client, is_deleted=False)
        except POC.DoesNotExist:
            return Response(status=404)

        if request.method == 'PATCH':
            serializer = POCSerializer(poc, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                log_action(self.request.user, 'updated', 'POC', poc.id, f"Updated POC for client '{client.company_name}'")
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        elif request.method == 'DELETE':
            poc.is_deleted = True
            poc.deleted_at = timezone.now()
            poc.save()
            log_action(self.request.user, 'deleted', 'POC', poc.id, f"Deleted POC for client '{client.company_name}'")
            return Response(status=204)

    @action(detail=True, methods=['post'], url_path='documents')
    def upload_document(self, request, pk=None):
        client = self.get_object()
        serializer = ClientDocumentSerializer(data=request.data)
        if serializer.is_valid():
            doc = serializer.save(client=client, organization=client.organization)
            log_action(self.request.user, 'created', 'ClientDocument', doc.id, f"Uploaded document for client '{client.company_name}'")
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['delete'], url_path=r'documents/(?P<doc_id>[^/.]+)')
    def delete_document(self, request, pk=None, doc_id=None):
        client = self.get_object()
        try:
            doc = ClientDocument.objects.get(id=doc_id, client=client, is_deleted=False)
            doc.is_deleted = True
            doc.deleted_at = timezone.now()
            doc.save()
            log_action(self.request.user, 'deleted', 'ClientDocument', doc.id, f"Deleted document for client '{client.company_name}'")
            return Response(status=204)
        except ClientDocument.DoesNotExist:
            return Response(status=404)

    @action(detail=False, methods=['post'], url_path='import')
    def import_clients(self, request):
        return Response({"preview": [], "total_rows": 0, "valid_rows": 0, "error_rows": [], "import_token": "dummy_token"})

    @action(detail=False, methods=['post'], url_path='import/confirm')
    def confirm_import(self, request):
        return Response({"imported": 0})

    @action(detail=False, methods=['get'], url_path='export')
    def export_clients(self, request):
        return Response({"message": "CSV export not implemented fully yet."})
