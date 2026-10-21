from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("id", "username", "password", "role", "rate_per_minute")

    def validate(self, attrs):
        if attrs.get("role") == User.Role.PROVIDER and not attrs.get("rate_per_minute"):
            raise serializers.ValidationError({"rate_per_minute": "Providers must set a per-minute rate."})
        if attrs.get("role", User.Role.USER) == User.Role.USER:
            attrs["rate_per_minute"] = None
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "rate_per_minute")
