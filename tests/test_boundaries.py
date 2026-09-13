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


@override_settings(BILLING_ENABLED=True)
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
        unpaid = Workspace.objects.create(name='Unpaid')
        BillingAccount.objects.create(workspace=unpaid)
        Monitor.objects.create(workspace=unpaid, name='unpaid', url='https://example.com')
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

    def test_signup_creates_unpaid_workspace(self):
        self.client.logout()
        response = self.client.post('/accounts/signup/', {'username': 'new-user', 'email': 'new@example.com', 'password1': 'a-unique-long-password-xyz-123', 'password2': 'a-unique-long-password-xyz-123'})
        self.assertEqual(response.status_code, 302)
        workspace = Workspace.objects.get(memberships__user__username='new-user')
        self.assertFalse(workspace.billing.has_access)
        self.assertEqual(workspace.memberships.get().role, 'owner')

    @override_settings(MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_notification_provider_failure_keeps_incident_and_retries(self):
        from monitors.tasks import deliver_notifications
        result = CheckResult.objects.create(monitor=self.monitor, ok=False)
        apply_check_result(result)
        with patch('monitors.tasks.send_mail', side_effect=OSError('offline')):
            deliver_notifications()
        item = Notification.objects.get()
        self.assertEqual(item.attempts, 1)
        self.assertIsNone(item.delivered_at)
        self.assertGreater(item.next_attempt_at, timezone.now())
        self.assertTrue(Incident.objects.filter(ended_at=None).exists())

    def test_reports_are_idempotent_and_tenant_scoped(self):
        import tempfile
        from reports.tasks import generate_reports
        from reports.models import ReportExport
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            generate_reports()
            generate_reports()
            self.assertEqual(ReportExport.objects.count(), 1)
            export = ReportExport.objects.get()
            self.assertIn(b'sample_success_percent', export.file.read())
            other = Workspace.objects.create(name='Other')
            self.assertEqual(self.client.get(reverse('report-download', args=[other.pk, export.pk])).status_code, 404)
            response = self.client.get(reverse('report-download', args=[self.workspace.pk, export.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'sample_success_percent', b''.join(response.streaming_content))

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_processing_failure_is_not_acknowledged(self):
        event = {'id': 'evt_failed', 'type': 'customer.subscription.deleted', 'data': {'object': {'customer': 'cus_alice'}}}
        body = json.dumps(event).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b'whsec_test', timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
        with patch('billing.views.reconcile', side_effect=OSError('Stripe unavailable')):
            response = self.client.post('/billing/webhook/', body, content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature}')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(StripeEvent.objects.filter(event_id='evt_failed', processed_at__isnull=False).exists())

    @override_settings(BILLING_ENABLED=False)
    def test_free_monitor_creation_dispatch_and_execution_without_subscription(self):
        self.billing.subscription_status = ''
        self.billing.save()
        response = self.client.post(reverse('monitor-create', args=[self.workspace.pk]), {
            'name': 'Free monitor', 'url': 'https://example.com/',
            'interval_seconds': 30, 'timeout_seconds': 10, 'enabled': 'on',
        })
        self.assertEqual(response.status_code, 302)
        monitor = Monitor.objects.get(name='Free monitor')
        with patch('monitors.tasks.run_monitor.delay') as publish:
            dispatch_due_checks()
            self.assertEqual(publish.call_count, 2)
        job = CheckJob.objects.get(monitor=monitor)
        with patch('monitors.tasks.check_url', return_value={'ok': True, 'status_code': 200, 'latency_ms': 42}):
            run_monitor(job.pk)
        self.assertTrue(monitor.checks.get().ok)
        self.billing.refresh_from_db()
        self.assertEqual(self.billing.subscription_status, '')
        self.assertContains(self.client.get('/'), 'Free monitoring')
        self.assertEqual(self.client.get(reverse('monitor-detail', args=[self.workspace.pk, monitor.pk])).status_code, 200)
        other = Workspace.objects.create(name='Private workspace')
        other_monitor = Monitor.objects.create(workspace=other, name='Private monitor', url='https://example.com/')
        self.assertEqual(self.client.get(reverse('monitor-detail', args=[other.pk, other_monitor.pk])).status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_free_reports_and_worker_do_not_require_billing_record(self):
        import tempfile
        from reports.tasks import generate_reports
        from reports.models import ReportExport
        self.billing.delete()
        job = CheckJob.objects.create(monitor=self.monitor)
        with patch('monitors.tasks.check_url', return_value={'ok': True, 'status_code': 200}):
            run_monitor(job.pk)
        self.assertTrue(self.monitor.checks.get().ok)
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            generate_reports()
            self.assertEqual(ReportExport.objects.filter(workspace=self.workspace).count(), 1)

    @override_settings(BILLING_ENABLED=False, STRIPE_SECRET_KEY='sk_test_unused', STRIPE_WEBHOOK_SECRET='whsec_unused', STRIPE_PRICE_ID='price_unused')
    def test_disabled_billing_never_calls_stripe_even_if_credentials_exist(self):
        from billing.tasks import reconcile_accounts
        with patch('billing.views.client') as client, patch('billing.tasks.reconcile') as reconcile:
            for endpoint in ('checkout', 'portal'):
                self.assertEqual(self.client.post(reverse(endpoint, args=[self.workspace.pk])).status_code, 409)
            self.assertEqual(self.client.post('/billing/webhook/', '{}', content_type='application/json').status_code, 404)
            reconcile_accounts()
            client.assert_not_called()
            reconcile.assert_not_called()
        self.assertContains(self.client.get(reverse('subscribe', args=[self.workspace.pk])), 'Monitoring is free')
