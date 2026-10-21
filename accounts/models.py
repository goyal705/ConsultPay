from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "USER", "User"
        PROVIDER = "PROVIDER", "Provider"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    rate_per_minute = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    @property
    def is_provider(self):
        return self.role == self.Role.PROVIDER
