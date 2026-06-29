from django.contrib import admin
from clients.models import Client, ClientDocument, POC

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'company_name', 'industry', 'city', 'status', 'created_at']
    list_filter = ['status', 'industry', 'country']
    search_fields = ['company_name', 'client_name', 'email', 'client_id']

admin.site.register(ClientDocument)
admin.site.register(POC)
