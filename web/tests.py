from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from wallet.models import Recharge, Wallet

User = get_user_model()


class WebSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass1234")
        self.provider = User.objects.create_user(
            "drbob", password="pass1234", role=User.Role.PROVIDER, rate_per_minute=Decimal("50")
        )

    def test_pages_render(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)
        self.assertEqual(self.client.get("/register/").status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_register_provider(self):
        res = self.client.post(
            "/register/",
            {"username": "drcarol", "password1": "S3cure-pass!", "password2": "S3cure-pass!",
             "role": "PROVIDER", "rate_per_minute": "30"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(User.objects.get(username="drcarol").is_provider)

    def test_recharge_and_book_through_ui(self):
        self.client.force_login(self.user)
        self.client.post("/recharge/", {"amount": "300"})
        ref = Recharge.objects.get(user=self.user).reference
        self.client.post(f"/recharge/{ref}/callback/", {"status": "success"})
        self.client.post(f"/recharge/{ref}/callback/", {"status": "success"})
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("300"))

        res = self.client.post("/sessions/new/", {"provider": self.provider.pk}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Session #")

        self.client.force_login(self.provider)
        session_id = self.provider.provider_sessions.get().pk
        self.client.post(f"/sessions/{session_id}/accept/")
        self.client.force_login(self.user)
        res = self.client.post(f"/sessions/{session_id}/start/", follow=True)
        self.assertContains(res, "In progress")
        self.assertEqual(self.client.post(f"/sessions/{session_id}/bill/").json()["status"], "in_progress")
