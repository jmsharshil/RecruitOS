"""
candidates/filters.py

django-filters FilterSet classes for Candidate and Application resources.
Registered on the respective ViewSets via filterset_class.
"""
import django_filters
from candidates.models import Candidate, Application


class CandidateFilterSet(django_filters.FilterSet):
    """
    Filter candidates by:
      - name / email / contact (search param handled by SearchFilter on ViewSet)
      - current_location, current_company, education (icontains)
      - is_duplicate
      - created range
    Note: CTC, notice_period, experience_min/max filters moved to ApplicationFilterSet
    as those fields now live on the Application model (per-job data).
    """
    current_location   = django_filters.CharFilter(field_name='current_location', lookup_expr='icontains')
    is_duplicate       = django_filters.BooleanFilter(field_name='is_duplicate')
    education          = django_filters.CharFilter(field_name='education', lookup_expr='icontains')
    current_company    = django_filters.CharFilter(field_name='current_company', lookup_expr='icontains')
    created_after      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before     = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = Candidate
        fields = [
            'current_location', 'is_duplicate',
            'education', 'current_company',
            'created_after', 'created_before',
        ]


class ApplicationFilterSet(django_filters.FilterSet):
    """
    Filter applications by:
      - status, job, candidate_name, stage_name
      - notice_period, current_ctc, expected_ctc (range filters)
      - created/share date range
    Note: Fields like current_ctc, expected_ctc, notice_period, reason_for_change
    now live on Application (moved from Candidate).
    """
    status             = django_filters.CharFilter(field_name='status', lookup_expr='exact')
    job                = django_filters.UUIDFilter(field_name='job__id')
    candidate_name     = django_filters.CharFilter(field_name='candidate__candidate_name', lookup_expr='icontains')
    stage_name         = django_filters.CharFilter(field_name='current_stage__name', lookup_expr='icontains')
    notice_period      = django_filters.CharFilter(field_name='notice_period', lookup_expr='icontains')
    current_ctc_min    = django_filters.NumberFilter(field_name='current_ctc', lookup_expr='gte')
    current_ctc_max    = django_filters.NumberFilter(field_name='current_ctc', lookup_expr='lte')
    expected_ctc_min   = django_filters.NumberFilter(field_name='expected_ctc', lookup_expr='gte')
    expected_ctc_max   = django_filters.NumberFilter(field_name='expected_ctc', lookup_expr='lte')
    created_after      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before     = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = Application
        fields = [
            'status', 'job', 'candidate_name', 'stage_name', 'notice_period',
            'current_ctc_min', 'current_ctc_max', 'expected_ctc_min',
            'expected_ctc_max', 'created_after', 'created_before',
        ]
