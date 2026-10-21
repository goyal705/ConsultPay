from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "role", "rate_per_minute", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role", "rate_per_minute")}),)
