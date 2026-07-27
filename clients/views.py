from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from clients.models import Client, POC, ClientDocument, ClientStatus
from clients.serializers import ClientListSerializer, ClientDetailSerializer, POCSerializer, ClientDocumentSerializer
from clients.filters import ClientFilterSet
from common.permissions import IsAdminOrManager, IsAdmin
from accounts.models import UserRole
from audit.utils import log_action

class ClientViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ClientFilterSet
    search_fields   = ['company_name', 'client_name', 'email', 'industry', 'city']
    ordering_fields = ['company_name', 'status', 'created_at', 'updated_at', 'agreement_date']
    ordering        = ['-created_at']
    parser_classes  = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action == 'list':
            return ClientListSerializer
        return ClientDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Client.objects.filter(
            is_deleted=False,
            organization=user.organization
        ).select_related('created_by')

        # Prefetch for detail view to optimize pocs/documents/stats (avoids N+1)
        if self.action in ('retrieve', 'change_status', 'add_poc', 'manage_poc', 'upload_document', 'delete_document'):
            qs = qs.prefetch_related('pocs', 'documents', 'jobs')

        if user.role in (UserRole.ADMIN, UserRole.MANAGER):
            return qs
        elif user.role == UserRole.RECRUITER:
            return qs.filter(
                jobs__is_deleted=False,
                jobs__assigned_recruiters=user
            ).distinct()
        return Client.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        # Mutating actions (create, update, pocs, documents, status) restricted to admin/manager
        return [IsAdminOrManager()]

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
        log_action(
            self.request.user, 'deleted', 'Client', instance.id,
            f"Deleted client '{instance.company_name}'"
        )

    @action(detail=True, methods=['patch'], url_path='status')
    def change_status(self, request, pk=None):
        """Update client status (active/inactive/on-hold). Mirrors Job change_status.
        Takes full status in body. Logs action. Uses normalized errors.
        """
        client = self.get_object()
        status_val = request.data.get('status')
        if status_val in dict(ClientStatus.choices):
            client.status = status_val
            client.save()
            log_action(
                self.request.user, 'updated', 'Client', client.id,
                f"Status changed to {status_val} for client '{client.company_name}'"
            )
            return Response({'status': client.status})
        raise ValidationError({"error": "Invalid status"})

    @action(detail=True, methods=['post'], url_path='pocs')
    def add_poc(self, request, pk=None):
        """Add POC to client. Body takes all POC fields (name, email, poc_type, etc.).
        Returns full serializer data on success. Uses ValidationError for errors.
        """
        client = self.get_object()
        serializer = POCSerializer(data=request.data)
        if serializer.is_valid():
            poc = serializer.save(client=client, organization=client.organization)
            log_action(self.request.user, 'created', 'POC', poc.id, f"Added POC for client '{client.company_name}'")
            return Response(serializer.data, status=201)
        raise ValidationError(serializer.errors)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'pocs/(?P<poc_id>[^/.]+)')
    def manage_poc(self, request, pk=None, poc_id=None):
        """Manage (update or soft-delete) a specific POC.
        PATCH body can contain any updatable POC fields.
        Full list semantics not used (single POC); errors normalized via handler.
        """
        client = self.get_object()
        try:
            poc = POC.objects.get(id=poc_id, client=client, is_deleted=False)
        except POC.DoesNotExist:
            raise NotFound({"error": "POC not found"})

        if request.method == 'PATCH':
            serializer = POCSerializer(poc, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                log_action(self.request.user, 'updated', 'POC', poc.id, f"Updated POC for client '{client.company_name}'")
                return Response(serializer.data)
            raise ValidationError(serializer.errors)
        elif request.method == 'DELETE':
            poc.is_deleted = True
            poc.deleted_at = timezone.now()
            poc.save()
            log_action(self.request.user, 'deleted', 'POC', poc.id, f"Deleted POC for client '{client.company_name}'")
            return Response(status=204)

    @action(detail=True, methods=['post'], url_path='documents', parser_classes=[MultiPartParser, FormParser])
    def upload_document(self, request, pk=None):
        """Upload document for client (multipart/form-data with 'file').
        Auto-sets file_name from uploaded file if not provided in body.
        Returns serialized doc (201). Consistent ValidationError handling.
        """
        client = self.get_object()
        data = request.data.copy()
        if 'file' in request.FILES and not data.get('file_name'):
            data['file_name'] = request.FILES['file'].name

        serializer = ClientDocumentSerializer(data=data)
        if serializer.is_valid():
            doc = serializer.save(client=client, organization=client.organization)
            log_action(self.request.user, 'created', 'ClientDocument', doc.id, f"Uploaded document for client '{client.company_name}'")
            return Response(serializer.data, status=201)
        raise ValidationError(serializer.errors)

    @action(detail=True, methods=['delete'], url_path=r'documents/(?P<doc_id>[^/.]+)')
    def delete_document(self, request, pk=None, doc_id=None):
        """Soft-delete a client document.
        """
        client = self.get_object()
        try:
            doc = ClientDocument.objects.get(id=doc_id, client=client, is_deleted=False)
            doc.is_deleted = True
            doc.deleted_at = timezone.now()
            doc.save()
            log_action(self.request.user, 'deleted', 'ClientDocument', doc.id, f"Deleted document for client '{client.company_name}'")
            return Response(status=204)
        except ClientDocument.DoesNotExist:
            raise NotFound({"error": "Document not found"})