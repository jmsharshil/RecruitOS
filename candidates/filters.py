"""
candidates/filters.py

django-filters FilterSet classes for Candidate and Application resources.
Registered on the respective ViewSets via filterset_class.
"""
import django_filters
from django.db.models import Q
from candidates.models import Candidate, Application

class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass

class CharInContainsFilter(django_filters.CharFilter):
    def filter(self, qs, value):
        if not value:
            return qs
        values = [v.strip() for v in value.split(',') if v.strip()]
        if not values:
            return qs
        q = Q()
        lookup = self.lookup_expr or 'icontains'
        for v in values:
            q |= Q(**{f"{self.field_name}__{lookup}": v})
        return qs.filter(q)

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
    candidate_name     = django_filters.CharFilter(method='filter_candidate_name_or_role')
    email              = django_filters.CharFilter(method='filter_email_or_contact')
    contact            = CharInContainsFilter(field_name='contact', lookup_expr='icontains')
    current_profile    = CharInContainsFilter(field_name='current_profile', lookup_expr='icontains')
    experience         = CharInContainsFilter(field_name='experience', lookup_expr='icontains')
    current_location   = CharInContainsFilter(field_name='current_location', lookup_expr='icontains')
    current_company    = CharInContainsFilter(field_name='current_company', lookup_expr='icontains')
    education          = CharInContainsFilter(field_name='education', lookup_expr='icontains')
    skills             = CharInContainsFilter(field_name='skills', lookup_expr='icontains')
    tags               = CharInContainsFilter(field_name='tags', lookup_expr='icontains')
    is_duplicate       = django_filters.BooleanFilter(field_name='is_duplicate')
    uploaded_by        = CharInContainsFilter(field_name='uploaded_by__name', lookup_expr='icontains')
    created_after      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before     = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    experience_min     = django_filters.NumberFilter(method='filter_exp_min')
    experience_max     = django_filters.NumberFilter(method='filter_exp_max')

    class Meta:
        model = Candidate
        fields = [
            'candidate_name', 'email', 'contact', 'current_profile', 'experience',
            'current_location', 'current_company', 'education',
            'is_duplicate', 'uploaded_by', 'created_after', 'created_before',
            'experience_min', 'experience_max',
        ]

    def _extract_exp_number(self, exp_str):
        import re
        if not exp_str:
            return None
        match = re.search(r'\d+(\.\d+)?', str(exp_str))
        if match:
            return float(match.group())
        return None

    def filter_exp_min(self, queryset, name, value):
        valid_ids = []
        for candidate in queryset:
            exp_val = self._extract_exp_number(candidate.experience)
            if exp_val is not None and exp_val >= float(value):
                valid_ids.append(candidate.id)
        return queryset.filter(id__in=valid_ids)

    def filter_exp_max(self, queryset, name, value):
        valid_ids = []
        for candidate in queryset:
            exp_val = self._extract_exp_number(candidate.experience)
            if exp_val is not None and exp_val <= float(value):
                valid_ids.append(candidate.id)
        return queryset.filter(id__in=valid_ids)

    def filter_candidate_name_or_role(self, queryset, name, value):
        if not value:
            return queryset
        values = [v.strip() for v in value.split(',') if v.strip()]
        if not values:
            return queryset
        q = Q()
        for v in values:
            q |= Q(candidate_name__icontains=v) | Q(current_profile__icontains=v)
        return queryset.filter(q)

    def filter_email_or_contact(self, queryset, name, value):
        if not value:
            return queryset
        values = [v.strip() for v in value.split(',') if v.strip()]
        if not values:
            return queryset
        q = Q()
        for v in values:
            q |= Q(email__icontains=v) | Q(contact__icontains=v)
        return queryset.filter(q)


class ApplicationFilterSet(django_filters.FilterSet):
    """
    Filter applications by:
      - status, job, candidate_name, stage_name
      - notice_period, current_ctc, expected_ctc (range filters)
      - created/share date range
    Note: Fields like current_ctc, expected_ctc, notice_period, reason_for_change
    now live on Application (moved from Candidate).
    """
    status             = CharInFilter(field_name='status', lookup_expr='in')
    job                = django_filters.UUIDFilter(field_name='job__id')
    candidate_name     = django_filters.CharFilter(method='filter_candidate_name_or_role')
    stage_name         = CharInContainsFilter(field_name='current_stage__name', lookup_expr='icontains')
    notice_period      = CharInContainsFilter(field_name='notice_period', lookup_expr='icontains')
    current_ctc        = CharInContainsFilter(field_name='current_ctc', lookup_expr='icontains')
    expected_ctc       = CharInContainsFilter(field_name='expected_ctc', lookup_expr='icontains')
    manager_review_status = CharInFilter(field_name='manager_review_status', lookup_expr='in')
    created_after      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before     = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    
    # Exact multi-select filters
    job_in             = CharInFilter(field_name='job__id', lookup_expr='in')

    class Meta:
        model = Application
        fields = [
            'status', 'job', 'candidate_name', 'stage_name', 'notice_period',
            'current_ctc', 'expected_ctc',
            'created_after', 'created_before', 'manager_review_status'
        ]

    def filter_candidate_name_or_role(self, queryset, name, value):
        if not value:
            return queryset
        values = [v.strip() for v in value.split(',') if v.strip()]
        if not values:
            return queryset
        q = Q()
        for v in values:
            q |= Q(candidate__candidate_name__icontains=v) | Q(candidate__current_profile__icontains=v)
        return queryset.filter(q)
