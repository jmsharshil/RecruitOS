from rest_framework import serializers
from clients.models import Client, POC, ClientDocument
from accounts.serializers import UserBriefSerializer

class POCSerializer(serializers.ModelSerializer):
    class Meta:
        model = POC
        fields = '__all__'
        read_only_fields = ['id', 'client', 'created_at', 'updated_at']

class ClientDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDocument
        fields = '__all__'
        read_only_fields = ['id', 'client', 'uploaded_at']

class ClientSerializer(serializers.ModelSerializer):
    pocs = serializers.SerializerMethodField()
    documents = ClientDocumentSerializer(many=True, read_only=True)
    created_by = UserBriefSerializer(read_only=True)
    stats = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['id', 'client_id', 'created_at', 'updated_at', 'created_by', 'is_deleted', 'deleted_at']

    def get_pocs(self, obj):
        pocs = obj.pocs.all()
        return {
            'hiring': POCSerializer(pocs.filter(poc_type='hiring'), many=True).data,
            'payment': POCSerializer(pocs.filter(poc_type='payment'), many=True).data,
        }

    def get_stats(self, obj):
        # We'll compute these dynamically. Since jobs are reverse fk.
        open_jobs = obj.jobs.filter(status='open').count()
        candidates = getattr(obj, '_prefetched_candidates_count', None)
        if candidates is None:
            # Not optimal for lists, but acceptable for detail views
            candidates_submitted = sum(job.candidates.filter(status='sent-to-client').count() for job in obj.jobs.all())
            hired_count = sum(job.candidates.filter(status='hired').count() for job in obj.jobs.all())
        else:
            candidates_submitted = 0
            hired_count = 0
            
        return {
            "open_jobs": open_jobs,
            "candidates_submitted": candidates_submitted,
            "hired_count": hired_count
        }
