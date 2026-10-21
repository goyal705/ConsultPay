from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("recharge/", views.recharge_create, name="recharge"),
    path("recharge/<str:reference>/callback/", views.recharge_callback, name="recharge_callback"),
    path("sessions/new/", views.session_create, name="session_create"),
    path("sessions/<int:pk>/", views.session_detail, name="session"),
    path("sessions/<int:pk>/bill/", views.session_bill, name="session_bill"),
    path("sessions/<int:pk>/<str:action>/", views.session_action, name="session_action"),
]
