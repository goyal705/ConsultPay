from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", lambda request: JsonResponse({"ok": True})),
    path("api/auth/", include("accounts.urls")),
    path("api/wallet/", include("wallet.urls")),
    path("api/sessions/", include("consultations.urls")),
    path("", include("web.urls")),
]
