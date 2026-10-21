from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import ProviderSerializer

from .models import ConsultationSession

User = get_user_model()


class SessionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    provider = ProviderSerializer(read_only=True)
    elapsed_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationSession
        fields = (
            "id",
            "user",
            "provider",
            "status",
            "rate_per_minute",
            "started_at",
            "ended_at",
            "elapsed_seconds",
            "billed_minutes",
            "billed_amount",
            "talk_seconds",
            "ended_by",
            "end_reason",
            "created_at",
        )

    def get_elapsed_seconds(self, obj):
        return obj.elapsed_seconds()


class ProviderField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return User.objects.filter(role=User.Role.PROVIDER)


class CreateSessionSerializer(serializers.Serializer):
    provider_id = ProviderField(required=False, allow_null=True)


class AssignSerializer(serializers.Serializer):
    provider_id = ProviderField()


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
