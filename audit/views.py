from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from audit.models import AuditLog
from audit.serializers import AuditLogSerializer
from common.permissions import IsAdmin

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    def get_queryset(self):
        return AuditLog.objects.filter(organization=self.request.user.organization)

    @action(detail=False, methods=['get'], url_path='export')
    def export_logs(self, request):
        return Response({"message": "CSV export not implemented fully yet."})
