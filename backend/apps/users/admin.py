from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


class UserAdmin(BaseUserAdmin):
    list_display = ("email", "name", "last_name", "role", "is_staff")
    list_filter = ("is_staff", "role", "is_active")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "last_name", "role")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "last_name",
                    "password1",
                    "password2",
                    "role",
                ),
            },
        ),
    )
    search_fields = ("email", "name", "last_name")
    ordering = ("email",)


admin.site.register(User, UserAdmin)
