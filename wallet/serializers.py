from decimal import Decimal

from rest_framework import serializers

from .models import Recharge, Wallet, WalletTransaction


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ("id", "kind", "amount", "balance_after", "reference", "description", "created_at")


class WalletSerializer(serializers.ModelSerializer):
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ("balance", "updated_at", "recent_transactions")

    def get_recent_transactions(self, obj):
        return WalletTransactionSerializer(obj.transactions.all()[:20], many=True).data


class RechargeSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))

    class Meta:
        model = Recharge
        fields = ("id", "amount", "reference", "status", "created_at", "updated_at")
        read_only_fields = ("reference", "status")


class RechargeCallbackSerializer(serializers.Serializer):
    reference = serializers.CharField()
    status = serializers.ChoiceField(choices=[Recharge.Status.SUCCESS, Recharge.Status.FAILED])
