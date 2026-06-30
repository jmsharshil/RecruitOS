from django.contrib import admin
from clients.models import Client, ClientDocument, POC

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Enhanced Client admin with tenant info and better filters for UX."""
    list_display = ['client_id', 'company_name', 'industry', 'city', 'status', 'organization', 'created_at']
    list_filter = ['status', 'industry', 'country', 'organization']
    search_fields = ['company_name', 'client_name', 'email', 'client_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    """Document admin for client files with tenant isolation."""
    list_display = ['file_name', 'client', 'uploaded_at', 'organization']
    list_filter = ['organization']
    search_fields = ['file_name', 'client__company_name']
    readonly_fields = ['uploaded_at', 'created_at', 'updated_at']


@admin.register(POC)
class POCAdmin(admin.ModelAdmin):
    """POC admin with type filter and client relation."""
    list_display = ['name', 'poc_type', 'client', 'email', 'contact', 'organization']
    list_filter = ['poc_type', 'organization']
    search_fields = ['name', 'email', 'client__company_name', 'designation']
    readonly_fields = ['created_at', 'updated_at']
