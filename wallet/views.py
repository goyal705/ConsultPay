from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Recharge, Wallet
from .serializers import RechargeCallbackSerializer, RechargeSerializer, WalletSerializer
from .services import initiate_recharge, process_recharge_callback


class WalletView(APIView):
    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return Response(WalletSerializer(wallet).data)


class RechargeListCreateView(generics.ListCreateAPIView):
    serializer_class = RechargeSerializer

    def get_queryset(self):
        return Recharge.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = initiate_recharge(self.request.user, serializer.validated_data["amount"])


class RechargeCallbackView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        secret = settings.RECHARGE_WEBHOOK_SECRET
        if secret and request.headers.get("X-Webhook-Secret") != secret:
            return Response({"detail": "Invalid webhook secret."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RechargeCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        get_object_or_404(Recharge, reference=serializer.validated_data["reference"])

        recharge, applied = process_recharge_callback(**serializer.validated_data)
        data = RechargeSerializer(recharge).data
        data["applied"] = applied
        return Response(data)
