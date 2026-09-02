from rest_framework import serializers
from clients.models import Client, POC, ClientDocument, TeamMemberTrackerFormat
from accounts.serializers import UserBriefSerializer
from common.serializers import DateParserField, DateParserDateTimeField

class POCSerializer(serializers.ModelSerializer):
    poc_type = serializers.CharField(write_only=True, default='hiring')
    class Meta:
        model = POC
        exclude = ['poc_type']
        read_only_fields = ['id', 'client', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']

class ClientDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDocument
        fields = '__all__'
        read_only_fields = ['id', 'client', 'uploaded_at', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']

class TeamMemberTrackerFormatSerializer(serializers.ModelSerializer):
    team_member_details = serializers.SerializerMethodField()
    created_by = UserBriefSerializer(read_only=True)
    csv_file = serializers.FileField(required=False, write_only=True)
    xlsx_file = serializers.FileField(required=False, write_only=True)

    class Meta:
        model = TeamMemberTrackerFormat
        fields = '__all__'
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']

    def validate(self, attrs):
        csv_file = attrs.pop('csv_file', None)
        xlsx_file = attrs.pop('xlsx_file', None)
        
        if xlsx_file:
            import openpyxl
            try:
                wb = openpyxl.load_workbook(xlsx_file, data_only=True)
                ws = wb.active
                headers = []
                bg_color = None
                fg_color = None
                
                # Read the first row
                for cell in ws[1]:
                    if cell.value is not None and str(cell.value).strip():
                        headers.append(str(cell.value).strip())
                        # Extract colors from the first valid cell
                        if not bg_color and cell.fill and cell.fill.start_color and cell.fill.start_color.rgb:
                            val = cell.fill.start_color.rgb
                            if isinstance(val, str) and len(val) == 8:
                                bg_color = f"#{val[2:]}"
                            elif isinstance(val, str) and len(val) == 6:
                                bg_color = f"#{val}"
                        if not fg_color and cell.font and cell.font.color and cell.font.color.rgb:
                            val = cell.font.color.rgb
                            if isinstance(val, str) and len(val) == 8:
                                fg_color = f"#{val[2:]}"
                            elif isinstance(val, str) and len(val) == 6:
                                fg_color = f"#{val}"
                
                if headers:
                    attrs['columns'] = headers
                if bg_color:
                    attrs['header_color'] = bg_color
                if fg_color:
                    attrs['text_color'] = fg_color
            except Exception as e:
                raise serializers.ValidationError({"xlsx_file": f"Invalid XLSX file: {str(e)}"})
        elif csv_file:
            import csv
            try:
                decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
                reader = csv.reader(decoded_file)
                raw_headers = next(reader, [])
                headers = [h.strip() for h in raw_headers if h.strip()]
                if headers:
                    attrs['columns'] = headers
            except Exception as e:
                raise serializers.ValidationError({"csv_file": f"Invalid CSV file: {str(e)}"})
                
        return attrs

    def get_team_member_details(self, obj):
        details = {
            'id': obj.team_member_id,
            'name': None,
            'email': None,
            'phone_number': None
        }
        if not obj.client or not obj.client.team_members:
            return details
        
        for tm in obj.client.team_members:
            if isinstance(tm, dict) and str(tm.get('id')) == str(obj.team_member_id):
                details['name'] = tm.get('name')
                details['email'] = tm.get('email')
                details['phone_number'] = tm.get('phone_number')
                break
        return details

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.pop('client', None)
        ret.pop('organization', None)
        ret.pop('team_member_id', None)
        ret.pop('is_deleted', None)
        ret.pop('deleted_at', None)
        return ret


# ---------------------------------------------------------------------------
# List serializer — one query per row, no nested POCs/docs
# ---------------------------------------------------------------------------
class ClientListSerializer(serializers.ModelSerializer):
    open_jobs_count  = serializers.SerializerMethodField()
    created_by_name  = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'client_id', 'company_name',
            'city', 'state', 'country',
            'open_jobs_count', 'created_by_name', 'created_at',
        ]

    def get_open_jobs_count(self, obj):
        return obj.jobs.filter(is_deleted=False, status='open').count()

    def get_created_by_name(self, obj):
        return obj.created_by.name if obj.created_by else None


# ---------------------------------------------------------------------------
# Detail serializer — full data including POCs, documents, stats
# ---------------------------------------------------------------------------
class ClientDetailSerializer(serializers.ModelSerializer):
    documents      = serializers.SerializerMethodField()
    created_by     = UserBriefSerializer(read_only=True)
    stats          = serializers.SerializerMethodField()
    agreement_date = DateParserField(required=False, allow_null=True)
    # Audit fields can accept input in some cases (e.g. CSV import backfills)
    created_at     = DateParserDateTimeField(read_only=False, required=False)
    updated_at     = DateParserDateTimeField(read_only=False, required=False)
    deleted_at     = DateParserDateTimeField(read_only=False, required=False, allow_null=True)

    class Meta:
        model = Client
        exclude = [
            'alternative_email', 'alternative_contact', 'website', 'linkedin', 'client_location',
            'client_name', 'industry', 'status', 'email', 'contact'
        ]
        read_only_fields = ['id', 'client_id', 'created_by', 'is_deleted', 'organization']


    def get_documents(self, obj):
        return ClientDocumentSerializer(obj.documents.filter(is_deleted=False), many=True).data

    def get_stats(self, obj):
        jobs = obj.jobs.filter(is_deleted=False)
        open_jobs = jobs.filter(status='open').count()
        candidates_submitted = sum(
            j.applications.filter(status='sent-to-client', is_deleted=False).count()
            for j in jobs
        )
        hired_count = sum(
            j.applications.filter(status='hired', is_deleted=False).count()
            for j in jobs
        )
        return {
            'open_jobs':             open_jobs,
            'candidates_submitted':  candidates_submitted,
            'hired_count':           hired_count,
        }

    def validate_team_members(self, value):
        import uuid
        if not isinstance(value, list):
            return value
        for member in value:
            if isinstance(member, dict) and not member.get('id'):
                member['id'] = str(uuid.uuid4())
        return value

    def to_internal_value(self, data):
        """
        Support nested writable 'pocs' and 'documents' for create while keeping
        output format (grouped pocs + filtered docs) via method fields.
        This fixes POCs not being saved on client creation.
        """
        import json

        pocs_data = data.get('pocs') if hasattr(data, 'get') else None
        documents_data = data.get('documents') if hasattr(data, 'get') else None
        team_members_data = data.get('team_members') if hasattr(data, 'get') else None

        # Convert QueryDict to mutable dict if necessary
        if hasattr(data, '_mutable'):
            data = data.copy()

        if isinstance(pocs_data, str):
            try:
                pocs_data = json.loads(pocs_data)
            except json.JSONDecodeError:
                pass
                
        if isinstance(documents_data, str):
            try:
                documents_data = json.loads(documents_data)
            except json.JSONDecodeError:
                pass
                
        if isinstance(team_members_data, str):
            team_members_data = team_members_data.strip()
            if not team_members_data:
                data['team_members'] = []
            else:
                try:
                    data['team_members'] = json.loads(team_members_data)
                except json.JSONDecodeError:
                    raise serializers.ValidationError({'team_members': 'Invalid JSON string'})

        internal_value = super().to_internal_value(data)

        if pocs_data is not None:
            if isinstance(pocs_data, dict):  # support single POC object
                pocs_data = [pocs_data]
            poc_serializer = POCSerializer(
                data=pocs_data, many=True, context=self.context
            )
            if not poc_serializer.is_valid():
                raise serializers.ValidationError({'pocs': poc_serializer.errors})
            internal_value['pocs'] = poc_serializer.validated_data

        if documents_data is not None:
            if isinstance(documents_data, dict):
                documents_data = [documents_data]
            doc_serializer = ClientDocumentSerializer(
                data=documents_data, many=True, context=self.context
            )
            if not doc_serializer.is_valid():
                raise serializers.ValidationError({'documents': doc_serializer.errors})
            internal_value['documents'] = doc_serializer.validated_data

        return internal_value

    def create(self, validated_data):
        """
        Create client + nested POCs/ClientDocuments. Handles agreement_document
        (uploaded file) by auto-setting agreement_document_name from file.name.
        Use multipart/form-data for creates that include files (agreement_document).
        Nested 'documents' supports metadata but files prefer dedicated /documents/ action.
        Organization/created_by injected by perform_create().
        """
        pocs_data = validated_data.pop('pocs', [])
        documents_data = validated_data.pop('documents', [])

        # Auto-set name for agreement document if file uploaded
        agreement_file = validated_data.get('agreement_document')
        if agreement_file and hasattr(agreement_file, 'name'):
            validated_data['agreement_document_name'] = agreement_file.name

        client = super().create(validated_data)

        for poc_data in pocs_data:
            POC.objects.create(
                client=client,
                organization=client.organization,
                **poc_data
            )

        for doc_data in documents_data:
            ClientDocument.objects.create(
                client=client,
                organization=client.organization,
                **doc_data
            )

        return client

    def update(self, instance, validated_data):
        """
        Nested pocs/documents ignored on update (use dedicated add_poc /
        upload_document endpoints). Auto-handles agreement_document + name
        if a new file is provided in multipart update.
        """
        # Auto-set name for agreement document if new file uploaded
        agreement_file = validated_data.get('agreement_document')
        if agreement_file and hasattr(agreement_file, 'name'):
            validated_data['agreement_document_name'] = agreement_file.name

        validated_data.pop('pocs', None)
        validated_data.pop('documents', None)
        return super().update(instance, validated_data)
