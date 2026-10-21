from django.contrib import admin

from .models import ConsultationSession


@admin.register(ConsultationSession)
class ConsultationSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "status", "rate_per_minute", "billed_minutes", "billed_amount", "ended_by")
    list_filter = ("status", "ended_by")
