"""
jobs/filters.py

django-filters FilterSet for the Job resource.
Registered on JobViewSet via filterset_class.
"""
import django_filters
from jobs.models import Job


class JobFilterSet(django_filters.FilterSet):
    """
    Filter jobs by:
      - status (exact)
      - priority (exact)
      - job_mode (exact)
      - job_type (exact)
      - hiring_for (exact)
      - client (UUID)
      - min_experience_min / min_experience_max
      - target_closing_date range
      - skills_contains (case-insensitive partial match in JSON skills list)
      - search handled separately by SearchFilter on ViewSet
    """
    status          = django_filters.CharFilter(field_name='status', lookup_expr='exact')
    priority        = django_filters.CharFilter(field_name='priority', lookup_expr='exact')
    job_mode        = django_filters.CharFilter(field_name='job_mode', lookup_expr='exact')
    job_type        = django_filters.CharFilter(field_name='job_type', lookup_expr='exact')
    hiring_for      = django_filters.CharFilter(field_name='hiring_for', lookup_expr='exact')
    client          = django_filters.UUIDFilter(field_name='client__id')
    min_exp         = django_filters.NumberFilter(field_name='min_experience', lookup_expr='gte')
    max_exp         = django_filters.NumberFilter(field_name='max_experience', lookup_expr='lte')
    closing_after   = django_filters.DateFilter(field_name='target_closing_date', lookup_expr='gte')
    closing_before  = django_filters.DateFilter(field_name='target_closing_date', lookup_expr='lte')
    created_after   = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before  = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    location        = django_filters.CharFilter(field_name='location', lookup_expr='icontains')

    class Meta:
        model = Job
        fields = [
            'status', 'priority', 'job_mode', 'job_type', 'hiring_for',
            'client', 'min_exp', 'max_exp',
            'closing_after', 'closing_before',
            'created_after', 'created_before',
            'location',
        ]
