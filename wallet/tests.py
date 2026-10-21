from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.test import APITestCase

from .models import Recharge, Wallet
from .services import InsufficientBalance, debit, lock_wallet

User = get_user_model()


class RechargeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass1234")
        self.client.force_authenticate(self.user)

    def _initiate(self, amount="500"):
        res = self.client.post("/api/wallet/recharges/", {"amount": amount})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "pending")
        return res.data["reference"]

    def _callback(self, reference, status="success"):
        return self.client.post("/api/wallet/recharges/callback/", {"reference": reference, "status": status})

    def balance(self):
        return Wallet.objects.get(user=self.user).balance

    def test_wallet_created_with_zero_balance(self):
        res = self.client.get("/api/wallet/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["balance"]), Decimal("0"))

    def test_pending_recharge_does_not_credit(self):
        self._initiate()
        self.assertEqual(self.balance(), Decimal("0"))

    def test_duplicate_success_callback_credits_once(self):
        ref = self._initiate("500")

        first = self._callback(ref)
        second = self._callback(ref)

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data["applied"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["applied"])
        self.assertEqual(self.balance(), Decimal("500"))
        self.assertEqual(Wallet.objects.get(user=self.user).transactions.count(), 1)

    def test_failed_callback_does_not_credit_and_is_final(self):
        ref = self._initiate("500")
        self._callback(ref, "failed")
        res = self._callback(ref, "success")

        self.assertFalse(res.data["applied"])
        self.assertEqual(Recharge.objects.get(reference=ref).status, "failed")
        self.assertEqual(self.balance(), Decimal("0"))

    def test_unknown_reference_returns_404(self):
        self.assertEqual(self._callback("nope").status_code, 404)

    def test_invalid_amount_rejected(self):
        res = self.client.post("/api/wallet/recharges/", {"amount": "-10"})
        self.assertEqual(res.status_code, 400)

    def test_debit_never_makes_balance_negative(self):
        Wallet.objects.filter(user=self.user).update(balance=Decimal("40"))
        with self.assertRaises(InsufficientBalance):
            with transaction.atomic():
                debit(lock_wallet(self.user), Decimal("50"), "test-debit")
        self.assertEqual(self.balance(), Decimal("40"))
