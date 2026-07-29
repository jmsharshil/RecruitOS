from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.utils.html import format_html
from accounts.models import User, Organization


# Customize Admin Site for better UX and branding
admin.site.site_header = format_html('<span style="color: #1e40af; font-weight: bold;">RecruitSmart ATS</span> Administration')
admin.site.site_title = "RecruitSmart ATS Admin"
admin.site.index_title = "Multi-Tenant Recruitment Dashboard"
admin.site.site_url = None  # Hide the "View site" link if no frontend

@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    """Enhanced User admin with organization scoping and better UX."""
    list_display = ['name', 'email', 'role', 'organization', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'organization']
    search_fields = ['name', 'email']
    ordering = ['-date_joined']
    readonly_fields = ['date_joined', 'last_login']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'organization', 'role')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2', 'role', 'organization'),
        }),
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Organization admin for multi-tenancy management (superuser only)."""
    list_display = ['name', 'id', 'created_at', 'user_count']
    search_fields = ['name']
    readonly_fields = ['id', 'created_at']
    ordering = ['name']

    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Users'
