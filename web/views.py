from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from consultations import services
from consultations.models import ConsultationSession
from wallet.models import Recharge, Wallet
from wallet.services import initiate_recharge, process_recharge_callback

from .forms import BookSessionForm, RechargeForm, RegisterForm

Status = ConsultationSession.Status

SESSION_ACTIONS = {
    "accept": services.accept,
    "start": services.start,
    "end": services.end,
    "cancel": services.cancel,
}


def available_actions(session, user):
    if user.pk == session.user_id:
        return {
            Status.ASSIGNED: ["cancel"],
            Status.ACCEPTED: ["start", "cancel"],
            Status.IN_PROGRESS: ["end"],
            Status.UNASSIGNED: ["cancel"],
        }.get(session.status, [])
    return {
        Status.ASSIGNED: ["accept", "cancel"],
        Status.ACCEPTED: ["cancel"],
        Status.IN_PROGRESS: ["end"],
    }.get(session.status, [])


def _my_session(request, pk):
    session = get_object_or_404(ConsultationSession.objects.select_related("user", "provider"), pk=pk)
    if request.user.pk not in (session.user_id, session.provider_id):
        raise Http404
    return session


def login_view(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("web:dashboard")
    return render(request, "login.html", {"form": form})


def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created.")
        return redirect("web:dashboard")
    return render(request, "register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("web:login")


@login_required
def dashboard(request):
    user = request.user
    wallet, _ = Wallet.objects.get_or_create(user=user)
    sessions = ConsultationSession.objects.filter(Q(user=user) | Q(provider=user)).select_related("user", "provider")
    return render(
        request,
        "dashboard.html",
        {
            "wallet": wallet,
            "transactions": wallet.transactions.all()[:10],
            "recharges": user.recharges.all()[:10],
            "sessions": sessions,
            "recharge_form": RechargeForm(),
            "book_form": BookSessionForm(),
        },
    )


@login_required
@require_POST
def recharge_create(request):
    form = RechargeForm(request.POST)
    if form.is_valid():
        recharge = initiate_recharge(request.user, form.cleaned_data["amount"])
        messages.info(request, f"Recharge of {recharge.amount} is pending. Simulate the payment callback below.")
    else:
        messages.error(request, "Enter a valid amount.")
    return redirect("web:dashboard")


@login_required
@require_POST
def recharge_callback(request, reference):
    get_object_or_404(Recharge, reference=reference, user=request.user)
    result = request.POST.get("status")
    if result not in (Recharge.Status.SUCCESS, Recharge.Status.FAILED):
        messages.error(request, "Invalid status.")
        return redirect("web:dashboard")
    recharge, applied = process_recharge_callback(reference, result)
    if not applied:
        messages.warning(request, f"Callback ignored, recharge is already {recharge.status}.")
    elif recharge.status == Recharge.Status.SUCCESS:
        messages.success(request, f"Wallet credited with {recharge.amount}.")
    else:
        messages.error(request, "Recharge marked as failed.")
    return redirect("web:dashboard")


@login_required
@require_POST
def session_create(request):
    form = BookSessionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick a provider.")
        return redirect("web:dashboard")
    try:
        session = services.create_session(request.user, form.cleaned_data["provider"])
    except services.SessionError as e:
        messages.error(request, str(e))
        return redirect("web:dashboard")
    messages.success(request, f"Session #{session.pk} requested.")
    return redirect("web:session", pk=session.pk)


@login_required
def session_detail(request, pk):
    session = _my_session(request, pk)
    wallet, _ = Wallet.objects.get_or_create(user=session.user)
    return render(
        request,
        "session_detail.html",
        {
            "session": session,
            "actions": available_actions(session, request.user),
            "is_owner": request.user.pk == session.user_id,
            "wallet": wallet,
        },
    )


@login_required
@require_POST
def session_action(request, pk, action):
    session = _my_session(request, pk)
    fn = SESSION_ACTIONS.get(action)
    if fn is None:
        raise Http404
    try:
        fn(session, request.user)
    except services.SessionError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Session {action} done.")
    return redirect("web:session", pk=pk)


@login_required
@require_POST
def session_bill(request, pk):
    session = services.bill(_my_session(request, pk))
    wallet = Wallet.objects.get(user=session.user)
    return JsonResponse(
        {
            "status": session.status,
            "billed_minutes": session.billed_minutes,
            "billed_amount": str(session.billed_amount),
            "balance": str(wallet.balance) if request.user.pk == session.user_id else None,
        }
    )
