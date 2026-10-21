from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from wallet.services import debit, lock_wallet

from .models import ConsultationSession

Status = ConsultationSession.Status
EndedBy = ConsultationSession.EndedBy

INSUFFICIENT_BALANCE = "Insufficient balance"

TRANSITIONS = {
    "assign": ({Status.UNASSIGNED}, Status.ASSIGNED),
    "accept": ({Status.ASSIGNED}, Status.ACCEPTED),
    "start": ({Status.ACCEPTED}, Status.IN_PROGRESS),
    "end": ({Status.IN_PROGRESS}, Status.COMPLETED),
    "cancel": ({Status.UNASSIGNED, Status.ASSIGNED, Status.ACCEPTED}, Status.CANCELLED),
}


class SessionError(Exception):
    pass


class NotAllowed(SessionError):
    pass


def _lock(session):
    return ConsultationSession.objects.select_for_update().get(pk=session.pk)


def _check_transition(session, action):
    allowed_from, _ = TRANSITIONS[action]
    if session.status not in allowed_from:
        raise SessionError(f"Cannot {action} a session that is '{session.status}'.")


def _role_of(session, actor):
    if actor.pk == session.user_id:
        return EndedBy.USER
    if session.provider_id and actor.pk == session.provider_id:
        return EndedBy.PROVIDER
    raise NotAllowed("You are not part of this session.")


def create_session(user, provider=None):
    if user.is_provider:
        raise NotAllowed("Providers cannot book sessions.")
    session = ConsultationSession.objects.create(user=user)
    if provider is not None:
        session = assign(session, user, provider)
    return session


def assign(session, actor, provider):
    with transaction.atomic():
        session = _lock(session)
        if actor.pk != session.user_id:
            raise NotAllowed("Only the session owner can assign a provider.")
        _check_transition(session, "assign")
        if not provider.is_provider or not provider.rate_per_minute:
            raise SessionError("Selected user is not a valid provider.")
        session.provider = provider
        session.status = Status.ASSIGNED
        session.save()
    return session


def accept(session, actor):
    with transaction.atomic():
        session = _lock(session)
        if actor.pk != session.provider_id:
            raise NotAllowed("Only the assigned provider can accept this session.")
        _check_transition(session, "accept")
        session.status = Status.ACCEPTED
        session.save()
    return session


def start(session, actor, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        session = _lock(session)
        if actor.pk != session.user_id:
            raise NotAllowed("Only the user can start the session.")
        _check_transition(session, "start")

        wallet = lock_wallet(session.user)
        if ConsultationSession.objects.filter(user=session.user, status=Status.IN_PROGRESS).exists():
            raise SessionError("You already have a session in progress.")

        rate = session.provider.rate_per_minute
        required = rate * settings.MIN_BALANCE_MINUTES
        if wallet.balance < required:
            raise SessionError(
                f"Insufficient balance. Need at least {required} "
                f"({settings.MIN_BALANCE_MINUTES} minutes), wallet has {wallet.balance}."
            )

        session.rate_per_minute = rate
        session.status = Status.IN_PROGRESS
        session.started_at = now
        try:
            session.save()
        except IntegrityError:
            raise SessionError("You already have a session in progress.")
    return session


def _charge_due_minutes(session, wallet, now):
    # charges every fully elapsed minute that hasn't been billed yet; False if wallet ran dry
    completed = session.elapsed_seconds(now) // 60
    rate = session.rate_per_minute
    while session.billed_minutes < completed:
        if wallet.balance < rate:
            return False
        minute = session.billed_minutes + 1
        debit(wallet, rate, f"session:{session.pk}:minute:{minute}", f"Session #{session.pk} - minute {minute}")
        session.billed_minutes = minute
        session.billed_amount += rate
    return True


def _finish(session, now, ended_by, reason=""):
    session.status = Status.COMPLETED
    session.ended_at = now
    session.ended_by = ended_by
    session.end_reason = reason
    session.talk_seconds = session.elapsed_seconds(now)
    session.save()


def bill(session, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        session = _lock(session)
        if session.status != Status.IN_PROGRESS:
            return session

        wallet = lock_wallet(session.user)
        paid = _charge_due_minutes(session, wallet, now)
        if not paid or wallet.balance < session.rate_per_minute:
            _finish(session, now, EndedBy.SYSTEM, INSUFFICIENT_BALANCE)
        else:
            session.save()
    return session


def end(session, actor, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        session = _lock(session)
        role = _role_of(session, actor)
        _check_transition(session, "end")

        wallet = lock_wallet(session.user)
        if _charge_due_minutes(session, wallet, now):
            _finish(session, now, role, f"Ended by {role}")
        else:
            _finish(session, now, EndedBy.SYSTEM, INSUFFICIENT_BALANCE)
    return session


def cancel(session, actor, reason=""):
    with transaction.atomic():
        session = _lock(session)
        role = _role_of(session, actor)
        _check_transition(session, "cancel")
        session.status = Status.CANCELLED
        session.ended_by = role
        session.end_reason = reason or f"Cancelled by {role}"
        session.save()
    return session


def bill_active_sessions(now=None):
    count = 0
    for session in ConsultationSession.objects.filter(status=Status.IN_PROGRESS):
        bill(session, now)
        count += 1
    return count
