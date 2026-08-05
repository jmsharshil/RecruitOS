from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from audit.models import AuditLog
from audit.serializers import AuditLogListSerializer, AuditLogDetailSerializer
from common.permissions import IsAdmin

import django_filters

class AuditLogFilter(django_filters.FilterSet):
    from_date = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    to_date = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    
    # Text-based filters for more flexibility
    user_name = django_filters.CharFilter(lookup_expr='icontains')
    user_email = django_filters.CharFilter(lookup_expr='icontains')
    entity = django_filters.CharFilter(lookup_expr='iexact')
    entity_id = django_filters.CharFilter(lookup_expr='exact')
    status_code = django_filters.NumberFilter(lookup_expr='exact')

    class Meta:
        model = AuditLog
        fields = [
            'event', 'action', 'method', 'user_role', 
            'from_date', 'to_date', 'user_name', 'user_email',
            'entity', 'entity_id', 'status_code'
        ]

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    
    # Search across all requested fields at once using ?search=
    search_fields = [
        'event', 'action', 'user_name', 'user_role', 
        'user_email', 'organization__name', 'method'
    ]
    
    # Use custom filterset for date range filtering
    filterset_class = AuditLogFilter
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AuditLogDetailSerializer
        return AuditLogListSerializer
    def get_queryset(self):
        return AuditLog.objects.filter(organization=self.request.user.organization)

    @action(detail=False, methods=['get'], url_path='export')
    def export_logs(self, request):
        return Response({"message": "CSV export not implemented fully yet."})
