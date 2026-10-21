from django.urls import path

from .views import RechargeCallbackView, RechargeListCreateView, WalletView

urlpatterns = [
    path("", WalletView.as_view(), name="wallet"),
    path("recharges/", RechargeListCreateView.as_view(), name="recharges"),
    path("recharges/callback/", RechargeCallbackView.as_view(), name="recharge-callback"),
]
