from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=User.Role.choices)
    rate_per_minute = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("1"), required=False, label="Rate per minute (providers)"
    )

    class Meta:
        model = User
        fields = ("username", "role", "rate_per_minute")

    def clean(self):
        data = super().clean()
        if data.get("role") == User.Role.PROVIDER:
            if not data.get("rate_per_minute"):
                self.add_error("rate_per_minute", "Providers must set a per-minute rate.")
        else:
            data["rate_per_minute"] = None
        return data


class RechargeForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))


class BookSessionForm(forms.Form):
    provider = forms.ModelChoiceField(queryset=User.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider"].queryset = User.objects.filter(role=User.Role.PROVIDER).order_by("username")
