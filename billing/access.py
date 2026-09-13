"""One entitlement policy for HTTP, scheduled work, workers and reports."""
from django.conf import settings
from django.db.models import Q


def subscription_has_access(status):
    return not settings.BILLING_ENABLED or status == 'active'


def workspace_has_access(workspace):
    if not settings.BILLING_ENABLED:
        return True
    account = getattr(workspace, 'billing', None)
    return bool(account and account.has_access)


def monitoring_access_q(billing_path='workspace__billing'):
    if not settings.BILLING_ENABLED:
        return Q()
    return Q(**{f'{billing_path}__subscription_status': 'active'})
