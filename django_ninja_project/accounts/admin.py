from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'name', 'lastName', 'role', 'is_staff')
    list_filter = ('is_staff', 'role', 'is_active')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'lastName', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'lastName', 'password1', 'password2', 'role'),
        }),
    )
    search_fields = ('email', 'name', 'lastName')
    ordering = ('email',)

admin.site.register(User, UserAdmin)