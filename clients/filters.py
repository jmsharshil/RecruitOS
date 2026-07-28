"""
clients/filters.py

django-filters FilterSet for Client resource.
Registered on ClientViewSet via filterset_class.
"""
import django_filters
from clients.models import Client


class ClientFilterSet(django_filters.FilterSet):
    """
    Filter clients by:
      - status (exact)
      - industry (icontains)
      - city, state, country (icontains)
      - created range
      - has_agreement (boolean: agreement_document__isnull)
      - commercial_decided (icontains on text field)
    SearchFilter on ViewSet handles company_name, client_name, email, industry.
    """
    status             = django_filters.CharFilter(field_name='status', lookup_expr='exact')
    industry           = django_filters.CharFilter(field_name='industry', lookup_expr='icontains')
    city               = django_filters.CharFilter(field_name='city', lookup_expr='icontains')
    state              = django_filters.CharFilter(field_name='state', lookup_expr='icontains')
    country            = django_filters.CharFilter(field_name='country', lookup_expr='icontains')
    created_after      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before     = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    agreement_date_after = django_filters.DateFilter(field_name='agreement_date', lookup_expr='gte')
    has_agreement      = django_filters.BooleanFilter(field_name='agreement_document', lookup_expr='isnull', exclude=True)
    commercial_decided = django_filters.CharFilter(field_name='commercial_decided', lookup_expr='icontains')

    class Meta:
        model = Client
        fields = [
            'status', 'industry', 'city', 'state', 'country',
            'created_after', 'created_before', 'agreement_date_after',
            'has_agreement', 'commercial_decided',
        ]
