from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from clients.models import Client, POC, ClientDocument, ClientStatus, TeamMemberTrackerFormat
from clients.serializers import ClientListSerializer, ClientDetailSerializer, POCSerializer, ClientDocumentSerializer, TeamMemberTrackerFormatSerializer
from clients.filters import ClientFilterSet
from common.permissions import IsAdminOrManager, IsAdmin
from accounts.models import UserRole
from audit.utils import log_action
from candidates.models import Application

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
        if self.action in ['list', 'retrieve', 'general_dropdown']:
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
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ClientDocument.DoesNotExist:
            return Response({"error": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='general-dropdown')
    def general_dropdown(self, request):
        """
        Returns a simplified list of clients and their team members for dropdowns.
        """
        clients = self.get_queryset()
        data = []
        for client in clients:
            data.append({
                "client": {
                    "client_id": str(client.id),
                    "name": client.company_name,
                    "email": client.email
                },
                "team_members": client.team_members if isinstance(client.team_members, list) else []
            })
        return Response({"clients_details": data}, status=status.HTTP_200_OK)

class TeamMemberTrackerFormatViewSet(viewsets.ModelViewSet):
    """
    CRUD for Tracker Formats specific to a client team member.
    Filter by ?client=<client_id>&team_member_id=<uuid>
    """
    serializer_class = TeamMemberTrackerFormatSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = TeamMemberTrackerFormat.objects.filter(
            organization=self.request.user.organization,
            is_deleted=False
        )
        client_id = self.request.query_params.get('client')
        team_member_id = self.request.query_params.get('team_member_id')
        
        if client_id:
            qs = qs.filter(client_id=client_id)
        if team_member_id:
            qs = qs.filter(team_member_id=team_member_id)
            
        return qs

    def perform_create(self, serializer):
        tracker = serializer.save(organization=self.request.user.organization, created_by=self.request.user)
        log_action(self.request.user, 'created', 'TeamMemberTrackerFormat', tracker.id, f"Created tracker format for team member {tracker.team_member_id}")

    def perform_update(self, serializer):
        tracker = serializer.save()
        log_action(self.request.user, 'updated', 'TeamMemberTrackerFormat', tracker.id, f"Updated tracker format for team member {tracker.team_member_id}")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_action(self.request.user, 'deleted', 'TeamMemberTrackerFormat', instance.id, f"Deleted tracker format for team member {instance.team_member_id}")

    @action(detail=False, methods=['post'], url_path='preview')
    def preview(self, request):
        """
        Expects:
        {
          "application_ids": ["id1", "id2"]
        }
        Returns the data for the requested applications formatted according to the saved tracker format.
        """
        app_ids = request.data.get('application_ids', [])

        if not app_ids:
            return Response({"error": "application_ids are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get applications
        apps = Application.objects.filter(id__in=app_ids, is_deleted=False).select_related('job', 'candidate')
        if not apps.exists():
            return Response({"error": "No valid applications found."}, status=status.HTTP_404_NOT_FOUND)
            
        first_app = apps.first()
        client_id = first_app.job.client_id
        team_member_id = first_app.job.team_member_id
        
        if not client_id or not team_member_id:
            return Response({"error": "The job associated with these applications does not have a client or team member assigned."}, status=status.HTTP_400_BAD_REQUEST)

        # Get team member details for tracker_receiver
        tracker_receiver = None
        if first_app.job.client and isinstance(first_app.job.client.team_members, list):
            for tm in first_app.job.client.team_members:
                if isinstance(tm, dict) and str(tm.get('id')) == str(team_member_id):
                    tracker_receiver = {
                        "id": tm.get('id'),
                        "name": tm.get('name'),
                        "email": tm.get('email')
                    }
                    break

        # Get the format
        try:
            tracker_format = TeamMemberTrackerFormat.objects.get(
                client_id=client_id, 
                team_member_id=team_member_id, 
                is_deleted=False
            )
            columns = tracker_format.columns
        except TeamMemberTrackerFormat.DoesNotExist:
            return Response({"error": "Tracker format not found for this team member , please create tracker for this team member first "}, status=status.HTTP_404_NOT_FOUND)
        
        tracker_preview = []
        for app in apps:
            candidate = app.candidate
            row = {
                "application_id": str(app.id)
            }
            for col in columns:
                col_norm = col.strip().lower().replace(' ', '_')
                
                if col_norm in ['candidate_name', 'name']:
                    row[col] = candidate.candidate_name
                elif col_norm == 'email':
                    row[col] = candidate.email
                elif col_norm in ['phone', 'contact', 'contacts']:
                    row[col] = candidate.contact
                elif col_norm in ['total_experience', 'experience', 'total_exp']:
                    row[col] = candidate.experience if candidate.experience else ""
                elif col_norm == 'current_company':
                    row[col] = candidate.current_company
                elif col_norm in ['current_designation', 'current_profile', 'designation', 'role']:
                    row[col] = candidate.current_profile
                elif col_norm in ['current_ctc', 'ctc', 'cctc']:
                    val = app.current_ctc if app.current_ctc else candidate.current_ctc
                    row[col] = str(val) if val else ""
                elif col_norm in ['expected_ctc', 'ectc']:
                    val = app.expected_ctc if app.expected_ctc else candidate.expected_ctc
                    row[col] = str(val) if val else ""
                elif col_norm == 'notice_period':
                    row[col] = app.notice_period if app.notice_period else candidate.notice_period
                elif col_norm in ['current_location', 'address', 'location']:
                    row[col] = candidate.current_location
                elif col_norm == 'preferred_location':
                    row[col] = app.preferred_location if app.preferred_location else candidate.preferred_location
                elif col_norm == 'hike':
                    val = app.hike if app.hike else candidate.hike
                    row[col] = val if val else ""
                elif col_norm in ['position_applied_for', 'position', 'job_title']:
                    row[col] = app.job.title if app.job else ""
                elif col_norm == 'skills':
                    row[col] = ", ".join(candidate.skills) if isinstance(candidate.skills, list) else candidate.skills
                elif col_norm == 'education':
                    row[col] = ", ".join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if isinstance(candidate.education, list) else candidate.education
                else:
                    custom_fields = app.tracker_custom_fields if isinstance(app.tracker_custom_fields, dict) else {}
                    row[col] = custom_fields.get(col, custom_fields.get(col_norm, ""))
                
                # Replace 'Not specified' with blank
                if isinstance(row.get(col), str) and row.get(col).strip().lower() == "not specified":
                    row[col] = ""
                    
            tracker_preview.append(row)

        return Response({
            "tracker_preview": tracker_preview, 
            "columns": columns,
            "tracker_receiver": tracker_receiver
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='preview-update')
    def preview_update(self, request):
        """
        Expects:
        {
            "updates": [
                {
                    "application_id": "uuid1",
                    "candidate_name": "New Name",
                    "current_ctc": "1500000"
                }
            ]
        }
        Updates the Candidate and Application records permanently.
        """
        updates = request.data.get('tracker_update', [])
        
        if not isinstance(updates, list):
            return Response({"error": "tracker_update must be a list of objects."}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = 0
        new_columns = set()
        
        for item in updates:
            app_id = item.get('application_id')
            if not app_id:
                continue

            try:
                app = Application.objects.get(id=app_id, is_deleted=False)
                candidate = app.candidate
                
                app_modified = False
                cand_modified = False

                standard_keys = {
                    'application_id', 'candidate_name', 'name', 'email', 'phone', 'contact', 'contacts', 
                    'total_experience', 'experience', 'total_exp', 'current_company', 
                    'current_designation', 'current_profile', 'designation', 'role', 'current_ctc', 'ctc', 'cctc', 
                    'expected_ctc', 'ectc', 'notice_period', 
                    'current_location', 'address', 'location', 'preferred_location', 'hike', 'skills', 'education'
                }
                
                normalized_item = {k.strip().lower().replace(' ', '_'): v for k, v in item.items()}

                # Handle all dynamic fields
                if not isinstance(app.tracker_custom_fields, dict):
                    app.tracker_custom_fields = {}
                    
                for key, val in item.items():
                    key_norm = key.strip().lower().replace(' ', '_')
                    if key_norm not in standard_keys:
                        app.tracker_custom_fields[key] = val
                        app_modified = True
                        new_columns.add(key)

                # Application fields
                if 'current_ctc' in normalized_item or 'ctc' in normalized_item or 'cctc' in normalized_item:
                    ctc_val = normalized_item.get('current_ctc') or normalized_item.get('ctc') or normalized_item.get('cctc')
                    try:
                        app.current_ctc = float(ctc_val) if ctc_val else None
                        app_modified = True
                    except ValueError: pass
                if 'expected_ctc' in normalized_item or 'ectc' in normalized_item:
                    val = normalized_item.get('expected_ctc') or normalized_item.get('ectc')
                    try:
                        app.expected_ctc = float(val) if val else None
                        app_modified = True
                    except ValueError: pass
                if 'hike' in normalized_item and hasattr(app, 'hike'):
                    app.hike = normalized_item['hike']
                    app_modified = True
                if 'notice_period' in normalized_item:
                    app.notice_period = normalized_item['notice_period']
                    app_modified = True

                # Candidate fields
                if 'candidate_name' in normalized_item or 'name' in normalized_item:
                    candidate.candidate_name = normalized_item.get('candidate_name') or normalized_item.get('name')
                    cand_modified = True
                if 'email' in normalized_item:
                    candidate.email = normalized_item['email']
                    cand_modified = True
                if 'phone' in normalized_item or 'contact' in normalized_item or 'contacts' in normalized_item:
                    candidate.contact = normalized_item.get('phone') or normalized_item.get('contact') or normalized_item.get('contacts')
                    cand_modified = True
                if 'total_experience' in normalized_item or 'experience' in normalized_item or 'total_exp' in normalized_item:
                    candidate.experience = normalized_item.get('total_experience') or normalized_item.get('experience') or normalized_item.get('total_exp')
                    cand_modified = True
                if 'current_company' in normalized_item:
                    candidate.current_company = normalized_item['current_company']
                    cand_modified = True
                if 'current_designation' in normalized_item or 'current_profile' in normalized_item or 'designation' in normalized_item or 'role' in normalized_item:
                    candidate.current_profile = normalized_item.get('current_designation') or normalized_item.get('current_profile') or normalized_item.get('designation') or normalized_item.get('role')
                    cand_modified = True
                if 'current_location' in normalized_item or 'address' in normalized_item or 'location' in normalized_item:
                    candidate.current_location = normalized_item.get('current_location') or normalized_item.get('address') or normalized_item.get('location')
                    cand_modified = True
                if 'preferred_location' in normalized_item:
                    candidate.preferred_location = normalized_item['preferred_location']
                    cand_modified = True
                if 'skills' in normalized_item:
                    # Depending on how skills are stored, simple split if it's a string
                    skills_val = normalized_item['skills']
                    if isinstance(skills_val, str):
                        candidate.skills = [s.strip() for s in skills_val.split(',') if s.strip()]
                    elif isinstance(skills_val, list):
                        candidate.skills = skills_val
                    cand_modified = True
                if 'education' in normalized_item:
                    candidate.education = normalized_item['education']
                    cand_modified = True

                if app_modified:
                    app.save()
                if cand_modified:
                    candidate.save()
                
                if app_modified or cand_modified:
                    updated_count += 1
            except Application.DoesNotExist:
                continue

        # Auto-sync columns to exactly match the keys sent in the payload
        if updates:
            first_item = updates[0]
            if first_item.get('application_id'):
                try:
                    first_app = Application.objects.select_related('job').get(id=first_item['application_id'])
                    client_id = first_app.job.client_id
                    team_member_id = first_app.job.team_member_id
                    
                    if client_id and team_member_id:
                        tracker_format = TeamMemberTrackerFormat.objects.get(
                            client_id=client_id,
                            team_member_id=team_member_id,
                            is_deleted=False
                        )
                        # Exact columns from frontend
                        desired_columns = [k for k in first_item.keys() if k != 'application_id']
                        
                        if tracker_format.columns != desired_columns:
                            tracker_format.columns = desired_columns
                            tracker_format.save()
                except (Application.DoesNotExist, TeamMemberTrackerFormat.DoesNotExist):
                    pass

        return Response({"message": f"Successfully updated {updated_count} applications."}, status=status.HTTP_200_OK)