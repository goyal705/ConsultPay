from django.contrib import admin

from .models import Recharge, Wallet, WalletTransaction

admin.site.register(Wallet)
admin.site.register(WalletTransaction)
admin.site.register(Recharge)
