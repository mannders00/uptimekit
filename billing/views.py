import logging
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from core.services import workspace_for
from core.observability import WEBHOOK_FAILURES
from .models import BillingAccount, StripeEvent
from .services import client, reconcile


@login_required
def subscribe(request, workspace_id):
    workspace = workspace_for(request.user, workspace_id)
    return render(request, 'billing.html', {'workspace': workspace, 'configured': bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID)})


@login_required
@require_POST
def checkout(request, workspace_id):
    workspace = workspace_for(request.user, workspace_id, owner=True)
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        return HttpResponse('Stripe is not configured yet.', status=503)
    with transaction.atomic():
        account = BillingAccount.objects.select_for_update().get(workspace=workspace)
        if account.has_access:
            return redirect('subscribe', workspace_id=workspace_id)
        if not account.stripe_customer_id:
            customer = client().v1.customers.create(params={'email': request.user.email, 'metadata': {'workspace_id': str(workspace_id)}}, options={'idempotency_key': f'workspace-{workspace_id}-customer'})
            account.stripe_customer_id = customer.id
            account.save(update_fields=['stripe_customer_id'])
        session = client().v1.checkout.sessions.create(params={
            'mode': 'subscription', 'customer': account.stripe_customer_id,
            'line_items': [{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
            'client_reference_id': str(workspace_id),
            'success_url': f'{settings.SITE_URL}/workspaces/{workspace_id}/billing/?processing=1',
            'cancel_url': f'{settings.SITE_URL}/workspaces/{workspace_id}/billing/',
        }, options={'idempotency_key': f'checkout-{workspace_id}-{int(timezone.now().timestamp()) // 1800}'})
    return redirect(session.url)


@login_required
@require_POST
def portal(request, workspace_id):
    workspace = workspace_for(request.user, workspace_id, owner=True)
    if not workspace.billing.stripe_customer_id:
        return redirect('subscribe', workspace_id=workspace_id)
    session = client().v1.billing_portal.sessions.create(params={'customer': workspace.billing.stripe_customer_id, 'return_url': settings.SITE_URL})
    return redirect(session.url)


@csrf_exempt
@require_POST
def webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    try:
        event = stripe.Webhook.construct_event(request.body, request.headers.get('Stripe-Signature', ''), settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        WEBHOOK_FAILURES.labels('signature').inc()
        return HttpResponse(status=400)
    try:
        with transaction.atomic():
            record, _ = StripeEvent.objects.get_or_create(event_id=event.id, defaults={'event_type': event.type})
            record = StripeEvent.objects.select_for_update().get(pk=record.pk)
            if record.processed_at:
                return HttpResponse(status=200)
            if event.type in {'checkout.session.completed', 'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'}:
                account = BillingAccount.objects.select_for_update().get(stripe_customer_id=event.data.object.customer)
                reconcile(account)
            record.processed_at = timezone.now()
            record.save(update_fields=['processed_at'])
    except Exception:
        WEBHOOK_FAILURES.labels('processing').inc()
        logging.getLogger(__name__).exception('stripe_webhook_processing_failed')
        return HttpResponse(status=503)  # Stripe retries; never acknowledge a lost update.
    return HttpResponse(status=200)
