import stripe
from django.conf import settings
from django.utils import timezone


def client():
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)


def reconcile(account):
    """Called under an account row lock: current Stripe state wins over arrival order."""
    subscriptions = client().v1.subscriptions.list(params={'customer': account.stripe_customer_id, 'status': 'all', 'limit': 100})
    matching = [s for s in subscriptions.auto_paging_iter() if any(
        item.price.id == settings.STRIPE_PRICE_ID for item in s['items'].data
    )]
    active = [s for s in matching if s.status == 'active']
    chosen = max(active or matching, key=lambda s: s.created, default=None)
    account.stripe_subscription_id = chosen.id if chosen else ''
    account.subscription_status = chosen.status if chosen else 'canceled'
    account.reconciled_at = timezone.now()
    account.save()
