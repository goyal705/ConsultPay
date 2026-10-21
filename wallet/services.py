from decimal import Decimal

from django.db import transaction

from .models import Recharge, Wallet, WalletTransaction


class InsufficientBalance(Exception):
    pass


def lock_wallet(user):
    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
    return wallet


def _post(wallet, kind, amount, reference, description):
    wallet.save(update_fields=["balance", "updated_at"])
    return WalletTransaction.objects.create(
        wallet=wallet,
        kind=kind,
        amount=amount,
        balance_after=wallet.balance,
        reference=reference,
        description=description,
    )


def credit(wallet, amount, reference, description=""):
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    wallet.balance += amount
    return _post(wallet, WalletTransaction.Kind.CREDIT, amount, reference, description)


def debit(wallet, amount, reference, description=""):
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if wallet.balance < amount:
        raise InsufficientBalance(f"Balance {wallet.balance} is less than {amount}")
    wallet.balance -= amount
    return _post(wallet, WalletTransaction.Kind.DEBIT, amount, reference, description)


def initiate_recharge(user, amount):
    return Recharge.objects.create(user=user, amount=amount)


def process_recharge_callback(reference, status):
    # returns (recharge, applied); once a recharge is final, repeat callbacks are no-ops
    if status not in (Recharge.Status.SUCCESS, Recharge.Status.FAILED):
        raise ValueError("status must be 'success' or 'failed'")

    with transaction.atomic():
        recharge = Recharge.objects.select_for_update().get(reference=reference)
        if recharge.status != Recharge.Status.PENDING:
            return recharge, False

        recharge.status = status
        recharge.save(update_fields=["status", "updated_at"])
        if status == Recharge.Status.SUCCESS:
            wallet = lock_wallet(recharge.user)
            credit(wallet, recharge.amount, f"recharge:{recharge.reference}", "Wallet recharge")
        return recharge, True
