from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from clients.models import Client, POC, ClientDocument
from clients.serializers import ClientSerializer, POCSerializer, ClientDocumentSerializer
from common.permissions import IsAdminOrManager, IsAdmin
from audit.utils import log_action

class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrManager]
    serializer_class = ClientSerializer

    def get_queryset(self):
        return Client.objects.filter(is_deleted=False, organization=self.request.user.organization)

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
        instance.save()
        log_action(self.request.user, 'deleted', 'Client', instance.id, f"Deleted client '{instance.company_name}'")

    @action(detail=True, methods=['post'], url_path='pocs')
    def add_poc(self, request, pk=None):
        client = self.get_object()
        serializer = POCSerializer(data=request.data)
        if serializer.is_valid():
            poc = serializer.save(client=client)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'pocs/(?P<poc_id>[^/.]+)')
    def manage_poc(self, request, pk=None, poc_id=None):
        client = self.get_object()
        try:
            poc = POC.objects.get(id=poc_id, client=client)
        except POC.DoesNotExist:
            return Response(status=404)

        if request.method == 'PATCH':
            serializer = POCSerializer(poc, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        elif request.method == 'DELETE':
            poc.delete()
            return Response(status=204)

    @action(detail=True, methods=['post'], url_path='documents')
    def upload_document(self, request, pk=None):
        client = self.get_object()
        serializer = ClientDocumentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(client=client)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=['delete'], url_path=r'documents/(?P<doc_id>[^/.]+)')
    def delete_document(self, request, pk=None, doc_id=None):
        client = self.get_object()
        try:
            doc = ClientDocument.objects.get(id=doc_id, client=client)
            doc.delete()
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
