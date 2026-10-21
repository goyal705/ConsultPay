from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from wallet.models import Wallet

from . import services
from .models import ConsultationSession

User = get_user_model()


class SessionTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass1234")
        self.provider = User.objects.create_user(
            "drbob", password="pass1234", role=User.Role.PROVIDER, rate_per_minute=Decimal("50")
        )

    def as_user(self):
        self.client.force_authenticate(self.user)

    def as_provider(self):
        self.client.force_authenticate(self.provider)

    def set_balance(self, amount):
        Wallet.objects.filter(user=self.user).update(balance=Decimal(amount))

    def balance(self):
        return Wallet.objects.get(user=self.user).balance

    def recharge(self, amount):
        self.as_user()
        ref = self.client.post("/api/wallet/recharges/", {"amount": amount}).data["reference"]
        self.client.post("/api/wallet/recharges/callback/", {"reference": ref, "status": "success"})

    def post(self, session_id, action, data=None):
        return self.client.post(f"/api/sessions/{session_id}/{action}/", data or {})

    def create_accepted_session(self):
        self.as_user()
        res = self.client.post("/api/sessions/", {"provider_id": self.provider.pk})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "assigned")
        session_id = res.data["id"]

        self.as_provider()
        res = self.post(session_id, "accept")
        self.assertEqual(res.data["status"], "accepted_by_provider")
        self.as_user()
        return session_id

    def started_session(self, minutes_ago):
        session_id = self.create_accepted_session()
        res = self.post(session_id, "start")
        self.assertEqual(res.status_code, 200, res.data)
        ConsultationSession.objects.filter(pk=session_id).update(
            started_at=timezone.now() - timedelta(minutes=minutes_ago, seconds=5)
        )
        return session_id


class InsufficientBalanceToStartTests(SessionTestBase):
    def test_cannot_start_with_less_than_five_minutes_balance(self):
        self.set_balance("249.99")
        session_id = self.create_accepted_session()

        res = self.post(session_id, "start")

        self.assertEqual(res.status_code, 400)
        self.assertIn("Insufficient balance", res.data["detail"])
        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(session.status, "accepted_by_provider")
        self.assertIsNone(session.started_at)
        self.assertEqual(self.balance(), Decimal("249.99"))

    def test_can_start_with_exactly_five_minutes_balance(self):
        self.set_balance("250")
        session_id = self.create_accepted_session()
        self.assertEqual(self.post(session_id, "start").status_code, 200)


class HappyPathTests(SessionTestBase):
    def test_full_flow_bills_two_minutes(self):
        self.recharge("1000")
        self.assertEqual(self.balance(), Decimal("1000"))

        session_id = self.started_session(minutes_ago=2)

        res = self.post(session_id, "bill")
        self.assertEqual(res.data["billed_minutes"], 2)
        self.assertEqual(self.balance(), Decimal("900"))

        res = self.post(session_id, "end")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "completed")
        self.assertEqual(res.data["ended_by"], "user")
        self.assertEqual(res.data["billed_minutes"], 2)
        self.assertEqual(Decimal(res.data["billed_amount"]), Decimal("100"))
        self.assertGreaterEqual(res.data["talk_seconds"], 120)
        self.assertEqual(self.balance(), Decimal("900"))

    def test_end_bills_unbilled_completed_minutes(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=3)

        res = self.post(session_id, "end")

        self.assertEqual(res.data["billed_minutes"], 3)
        self.assertEqual(self.balance(), Decimal("850"))

    def test_provider_can_end_session(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=1)
        self.as_provider()

        res = self.post(session_id, "end")

        self.assertEqual(res.data["ended_by"], "provider")
        self.assertEqual(self.balance(), Decimal("950"))


class BalanceRunsOutTests(SessionTestBase):
    def test_system_ends_session_when_next_minute_cannot_be_paid(self):
        self.set_balance("290")
        session_id = self.started_session(minutes_ago=7)

        res = self.post(session_id, "bill")

        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.ended_by, "system")
        self.assertEqual(session.end_reason, "Insufficient balance")
        self.assertEqual(session.billed_minutes, 5)
        self.assertEqual(session.billed_amount, Decimal("250"))
        self.assertIsNotNone(session.talk_seconds)
        self.assertEqual(self.balance(), Decimal("40"))

    def test_session_ends_as_soon_as_balance_cannot_cover_next_minute(self):
        self.set_balance("290")
        session_id = self.started_session(minutes_ago=5)

        self.post(session_id, "bill")

        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.ended_by, "system")
        self.assertEqual(self.balance(), Decimal("40"))

    def test_rate_change_after_start_does_not_affect_session(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=2)
        User.objects.filter(pk=self.provider.pk).update(rate_per_minute=Decimal("500"))

        res = self.post(session_id, "bill")

        self.assertEqual(Decimal(res.data["rate_per_minute"]), Decimal("50"))
        self.assertEqual(self.balance(), Decimal("900"))


class InvalidTransitionTests(SessionTestBase):
    def test_end_before_start_returns_400(self):
        session_id = self.create_accepted_session()
        res = self.post(session_id, "end")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Cannot end", res.data["detail"])

    def test_start_unaccepted_session_returns_400(self):
        self.set_balance("1000")
        self.as_user()
        session_id = self.client.post("/api/sessions/", {"provider_id": self.provider.pk}).data["id"]
        self.assertEqual(self.post(session_id, "start").status_code, 400)

    def test_accept_twice_returns_400(self):
        session_id = self.create_accepted_session()
        self.as_provider()
        self.assertEqual(self.post(session_id, "accept").status_code, 400)

    def test_cannot_cancel_running_session(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=0)
        self.assertEqual(self.post(session_id, "cancel").status_code, 400)

    def test_cannot_restart_completed_session(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=1)
        self.post(session_id, "end")
        self.assertEqual(self.post(session_id, "start").status_code, 400)

    def test_unassigned_session_flow(self):
        self.as_user()
        res = self.client.post("/api/sessions/", {})
        self.assertEqual(res.data["status"], "unassigned")
        session_id = res.data["id"]

        self.assertEqual(self.post(session_id, "start").status_code, 400)
        res = self.post(session_id, "assign", {"provider_id": self.provider.pk})
        self.assertEqual(res.data["status"], "assigned")
        self.assertEqual(self.post(session_id, "assign", {"provider_id": self.provider.pk}).status_code, 400)

    def test_user_cannot_accept_own_session(self):
        self.as_user()
        session_id = self.client.post("/api/sessions/", {"provider_id": self.provider.pk}).data["id"]
        self.assertEqual(self.post(session_id, "accept").status_code, 403)

    def test_provider_cannot_book_session(self):
        self.as_provider()
        self.assertEqual(self.client.post("/api/sessions/", {}).status_code, 403)

    def test_only_one_active_session_per_user(self):
        self.set_balance("1000")
        self.started_session(minutes_ago=0)
        second = self.create_accepted_session()

        res = self.post(second, "start")

        self.assertEqual(res.status_code, 400)
        self.assertIn("already have a session", res.data["detail"])


class DuplicateBillingTests(SessionTestBase):
    def test_billing_same_minute_twice_charges_once(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=1)

        self.post(session_id, "bill")
        self.post(session_id, "bill")
        self.post(session_id, "bill")

        session = ConsultationSession.objects.get(pk=session_id)
        self.assertEqual(session.billed_minutes, 1)
        self.assertEqual(self.balance(), Decimal("950"))
        self.assertEqual(Wallet.objects.get(user=self.user).transactions.filter(kind="debit").count(), 1)

    def test_service_billing_is_idempotent_for_same_time(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=0)
        session = ConsultationSession.objects.get(pk=session_id)
        at = session.started_at + timedelta(minutes=3, seconds=10)

        services.bill(session, now=at)
        services.bill(session, now=at)
        services.bill(session, now=at - timedelta(minutes=1))

        session.refresh_from_db()
        self.assertEqual(session.billed_minutes, 3)
        self.assertEqual(self.balance(), Decimal("850"))

    def test_partial_minute_is_not_billed(self):
        self.set_balance("1000")
        session_id = self.started_session(minutes_ago=0)
        res = self.post(session_id, "bill")
        self.assertEqual(res.data["billed_minutes"], 0)
        self.assertEqual(self.balance(), Decimal("1000"))

    def test_bill_active_sessions_command_helper(self):
        self.set_balance("1000")
        self.started_session(minutes_ago=2)
        self.assertEqual(services.bill_active_sessions(), 1)
        self.assertEqual(self.balance(), Decimal("900"))
