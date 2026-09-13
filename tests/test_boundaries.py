import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock
import httpx
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from billing.models import BillingAccount, StripeEvent
from core.models import Membership, Workspace
from monitors.forms import MonitorForm
from monitors.models import CheckJob, CheckResult, Incident, Monitor, Notification
from monitors.services import apply_check_result, check_url
from monitors.tasks import dispatch_due_checks, run_monitor, delete_old_checks


class Boundaries(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', email='alice@example.com', password='long-random-password-123')
        self.workspace = Workspace.objects.create(name='Alice')
        Membership.objects.create(user=self.user, workspace=self.workspace)
        self.billing = BillingAccount.objects.create(workspace=self.workspace, subscription_status='active', stripe_customer_id='cus_alice')
        self.monitor = Monitor.objects.create(workspace=self.workspace, name='Example', url='https://example.com')
        self.client.force_login(self.user)

    def test_tenant_queries_deny_read_edit_delete_and_billing(self):
        other = Workspace.objects.create(name='Other')
        BillingAccount.objects.create(workspace=other)
        monitor = Monitor.objects.create(workspace=other, name='Secret', url='https://example.com')
        for name in ('monitor-detail', 'monitor-edit', 'monitor-delete'):
            url = reverse(name, args=[other.pk, monitor.pk])
            self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('checkout', args=[other.pk])).status_code, 404)

    def test_member_cannot_manage_owner_billing(self):
        Membership.objects.filter(user=self.user).update(role='member')
        self.assertEqual(self.client.post(reverse('portal', args=[self.workspace.pk])).status_code, 404)

    def test_paid_gate_on_create_and_queued_execution(self):
        self.billing.subscription_status = 'canceled'
        self.billing.save()
        response = self.client.post(reverse('monitor-create', args=[self.workspace.pk]))
        self.assertEqual(response.status_code, 302)
        job = CheckJob.objects.create(monitor=self.monitor)
        with patch('monitors.tasks.check_url') as fetch:
            run_monitor(job.pk)
            fetch.assert_not_called()
        self.assertFalse(CheckResult.objects.exists())

    def test_url_and_interval_validation(self):
        for url in ['http://127.0.0.1', 'http://169.254.169.254/latest/meta-data/', 'http://[::1]/', 'http://localhost/', 'https://example.com:22/', 'https://user:pass@example.com/']:
            form = MonitorForm(data={'name': 'unsafe', 'url': url, 'interval_seconds': 60, 'timeout_seconds': 10})
            self.assertFalse(form.is_valid(), url)
        form = MonitorForm(data={'name': 'fast', 'url': 'https://example.com', 'interval_seconds': 1, 'timeout_seconds': 10})
        self.assertFalse(form.is_valid())

    def test_incident_state_and_out_of_order_results(self):
        now = timezone.now()
        first = CheckResult.objects.create(monitor=self.monitor, ok=False, checked_at=now)
        apply_check_result(first)
        apply_check_result(CheckResult.objects.create(monitor=self.monitor, ok=False, checked_at=now+timedelta(seconds=1)))
        self.assertEqual(Incident.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        apply_check_result(CheckResult.objects.create(monitor=self.monitor, ok=True, checked_at=now+timedelta(seconds=2)))
        apply_check_result(first)
        self.assertFalse(Incident.objects.filter(ended_at=None).exists())
        self.assertEqual(Notification.objects.count(), 2)

    def test_retention_preserves_incidents(self):
        result = CheckResult.objects.create(monitor=self.monitor, ok=False, checked_at=timezone.now()-timedelta(days=31))
        apply_check_result(result)
        delete_old_checks()
        self.assertFalse(CheckResult.objects.exists())
        self.assertEqual(Incident.objects.count(), 1)
        self.assertIsNone(Incident.objects.get().opening_check_id)

    def test_dispatcher_filters_and_recovers_publish_failure(self):
        Monitor.objects.create(workspace=self.workspace, name='disabled', url='https://example.com', enabled=False)
        Monitor.objects.create(workspace=self.workspace, name='future', url='https://example.com', next_check_at=timezone.now()+timedelta(days=1))
        with patch('monitors.tasks.run_monitor.delay', side_effect=ConnectionError):
            with self.assertRaises(ConnectionError):
                dispatch_due_checks()
        self.assertEqual(CheckJob.objects.count(), 1)
        with patch('monitors.tasks.run_monitor.delay') as publish:
            dispatch_due_checks()
            publish.assert_called_once_with(CheckJob.objects.get().pk)

    def test_duplicate_job_execution_is_idempotent(self):
        job = CheckJob.objects.create(monitor=self.monitor)
        with patch('monitors.tasks.check_url', return_value={'ok': False, 'error_message': 'ReadTimeout'}) as fetch:
            run_monitor(job.pk)
            run_monitor(job.pk)
        fetch.assert_called_once()
        self.assertEqual(CheckResult.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), 1)

    def test_dns_private_destination_never_fetched(self):
        with patch('monitors.services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('169.254.169.254', 80))]), patch('monitors.services.httpx.Client') as client:
            self.assertFalse(check_url('http://example.com', 1)['ok'])
            client.assert_not_called()

    def test_timeout_records_failure(self):
        with patch('monitors.services.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), patch('monitors.services.httpx.Client', side_effect=httpx.ReadTimeout('timeout')):
            result = check_url('https://example.com', 1)
            self.assertFalse(result['ok'])
            self.assertEqual(result['error_message'], 'ReadTimeout')

    def test_readiness_database_failure_and_metrics_auth(self):
        with patch.object(connection, 'cursor', side_effect=Exception('offline')):
            self.assertEqual(self.client.get('/health/ready').status_code, 503)
        self.assertEqual(self.client.get('/health/live').status_code, 200)
        self.assertEqual(self.client.get('/internal/metrics').status_code, 403)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_signed_webhooks_duplicate_and_invalid(self):
        event = {'id': 'evt_test', 'type': 'customer.subscription.updated', 'data': {'object': {'customer': 'cus_alice'}}}
        body = json.dumps(event).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(b'whsec_test', timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
        signature = f't={timestamp},v1={digest}'
        self.assertEqual(self.client.post('/billing/webhook/', body, content_type='application/json').status_code, 400)
        with patch('billing.views.reconcile') as reconcile:
            for _ in range(2):
                self.assertEqual(self.client.post('/billing/webhook/', body, content_type='application/json', HTTP_STRIPE_SIGNATURE=signature).status_code, 200)
            reconcile.assert_called_once()
        self.assertEqual(StripeEvent.objects.count(), 1)

    @override_settings(STRIPE_PRICE_ID='price_test')
    def test_reconcile_uses_current_subscription_not_event_order(self):
        from billing.services import reconcile
        subscription = MagicMock()
        subscription.id = 'sub_current'
        subscription.status = 'canceled'
        subscription.created = 10
        item = MagicMock()
        item.price.id = 'price_test'
        subscription.__getitem__.return_value.data = [item]
        with patch('billing.services.client') as client:
            client.return_value.v1.subscriptions.list.return_value.auto_paging_iter.return_value = iter([subscription])
            reconcile(self.billing)
        self.assertFalse(self.billing.has_access)
