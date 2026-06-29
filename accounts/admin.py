from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from accounts.models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    search_fields = ['name', 'email']
