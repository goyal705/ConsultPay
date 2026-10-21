from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConsultationSession(models.Model):
    class Status(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted_by_provider", "Accepted by provider"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class EndedBy(models.TextChoices):
        USER = "user", "User"
        PROVIDER = "provider", "Provider"
        SYSTEM = "system", "System"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="provider_sessions",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UNASSIGNED)

    # copied from the provider when the session starts, never changed after that
    rate_per_minute = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    billed_minutes = models.PositiveIntegerField(default=0)
    billed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    talk_seconds = models.PositiveIntegerField(null=True, blank=True)

    ended_by = models.CharField(max_length=10, choices=EndedBy.choices, blank=True)
    end_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="in_progress"),
                name="one_active_session_per_user",
            ),
        ]

    def __str__(self):
        return f"Session #{self.pk} ({self.status})"

    @property
    def is_active(self):
        return self.status == self.Status.IN_PROGRESS

    @property
    def is_closed(self):
        return self.status in (self.Status.COMPLETED, self.Status.CANCELLED)

    def elapsed_seconds(self, now=None):
        if not self.started_at:
            return 0
        end = self.ended_at or now or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    def current_rate(self):
        if self.rate_per_minute is not None:
            return self.rate_per_minute
        return self.provider.rate_per_minute if self.provider else None
