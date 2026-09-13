import logging
from celery import shared_task
from django.conf import settings
from django.db import transaction
from .models import BillingAccount
from .services import reconcile


@shared_task
def reconcile_accounts():
    if not settings.BILLING_ENABLED or not settings.STRIPE_SECRET_KEY:
        return
    for pk in BillingAccount.objects.exclude(stripe_customer_id='').values_list('pk', flat=True):
        try:
            with transaction.atomic():
                reconcile(BillingAccount.objects.select_for_update().get(pk=pk))
        except Exception:
            logging.getLogger(__name__).exception('billing_reconciliation_failed', extra={'billing_account_id': pk})
