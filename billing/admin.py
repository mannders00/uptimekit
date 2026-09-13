from django.contrib import admin

from .models import BillingAccount, StripeEvent

admin.site.register([BillingAccount, StripeEvent])
