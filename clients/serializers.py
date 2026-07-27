from rest_framework import serializers
from clients.models import Client, POC, ClientDocument
from accounts.serializers import UserBriefSerializer
from common.serializers import DateParserField, DateParserDateTimeField

class POCSerializer(serializers.ModelSerializer):
    class Meta:
        model = POC
        fields = '__all__'
        read_only_fields = ['id', 'client', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']

class ClientDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDocument
        fields = '__all__'
        read_only_fields = ['id', 'client', 'uploaded_at', 'created_at', 'updated_at', 'organization', 'is_deleted', 'deleted_at']


# ---------------------------------------------------------------------------
# List serializer — one query per row, no nested POCs/docs
# ---------------------------------------------------------------------------
class ClientListSerializer(serializers.ModelSerializer):
    open_jobs_count  = serializers.SerializerMethodField()
    created_by_name  = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'client_id', 'company_name', 'industry', 'status',
            'email', 'contact', 'city', 'state', 'country',
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
    pocs           = serializers.SerializerMethodField()
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
        fields = '__all__'
        read_only_fields = ['id', 'client_id', 'created_by', 'is_deleted', 'organization']

    def get_pocs(self, obj):
        pocs = obj.pocs.filter(is_deleted=False)
        return {
            'hiring':  POCSerializer(pocs.filter(poc_type='hiring'),  many=True).data,
            'payment': POCSerializer(pocs.filter(poc_type='payment'), many=True).data,
        }

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

    def to_internal_value(self, data):
        """
        Support nested writable 'pocs' and 'documents' for create while keeping
        output format (grouped pocs + filtered docs) via method fields.
        This fixes POCs not being saved on client creation.
        """
        if isinstance(data, dict):
            pocs_data = data.get('pocs')
            documents_data = data.get('documents')
        else:
            pocs_data = documents_data = None

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
