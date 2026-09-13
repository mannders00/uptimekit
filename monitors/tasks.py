import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from core.models import Heartbeat
from .models import CheckJob, CheckResult, Monitor, Notification
from .services import apply_check_result, check_url

logger = logging.getLogger(__name__)


@shared_task
def dispatch_due_checks():
    now = timezone.now()
    with transaction.atomic():
        Heartbeat.objects.update_or_create(name='dispatcher')
        due = Monitor.objects.select_for_update(skip_locked=True).filter(
            enabled=True, next_check_at__lte=now, workspace__billing__subscription_status='active'
        ).order_by('next_check_at')[:200]
        for monitor in due:
            CheckJob.objects.get_or_create(monitor=monitor, completed_at=None)
            monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
            monitor.save(update_fields=['next_check_at'])
    # Publishing is outside the claiming transaction. Retrying a job ID is safe.
    jobs = CheckJob.objects.filter(completed_at=None).filter(Q(published_at=None) | Q(published_at__lt=now - timedelta(minutes=2)))[:200]
    for job in jobs:
        run_monitor.delay(job.pk)
        CheckJob.objects.filter(pk=job.pk).update(published_at=now)


@shared_task(acks_late=True, reject_on_worker_lost=True)
def run_monitor(job_id):
    with transaction.atomic():
        job = CheckJob.objects.select_for_update().filter(pk=job_id).first()
        if not job or job.completed_at:
            return
        monitor = Monitor.objects.select_for_update(of=('self',)).select_related('workspace__billing').get(pk=job.monitor_id)
        if monitor.enabled and monitor.workspace.billing.has_access:
            result = CheckResult.objects.create(monitor=monitor, job=job, **check_url(monitor.url, monitor.timeout_seconds))
            apply_check_result(result)
            logger.info('monitor_check_complete', extra={'monitor_id': monitor.pk, 'check_id': result.pk, 'ok': result.ok, 'latency_ms': result.latency_ms})
        job.completed_at = timezone.now()
        job.save(update_fields=['completed_at'])
        Heartbeat.objects.update_or_create(name='worker')


@shared_task
def deliver_notifications():
    # Console output is explicitly not delivery evidence.
    if settings.MAILERS['default']['BACKEND'] in ('core.mail.DisabledEmailBackend', 'django.core.mail.backends.console.EmailBackend'):
        return
    for pk in Notification.objects.filter(delivered_at=None, next_attempt_at__lte=timezone.now()).values_list('pk', flat=True)[:50]:
        with transaction.atomic():
            item = Notification.objects.select_for_update(skip_locked=True).filter(pk=pk, delivered_at=None).first()
            if not item:
                continue
            monitor = item.incident.monitor
            item.attempts += 1
            try:
                recipients = list(monitor.workspace.memberships.values_list('user__email', flat=True))
                if not recipients:
                    raise ValueError('No recipients')
                delivered = send_mail(f'{item.kind.upper()}: {monitor.name}', f'{monitor.url}\nIncident {item.incident_id}: {item.kind}', settings.DEFAULT_FROM_EMAIL, recipients)
                if delivered != 1:
                    raise ValueError('Provider did not accept email')
                item.delivered_at = timezone.now()
                item.last_error = ''
            except Exception as exc:
                item.last_error = type(exc).__name__
                item.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(item.attempts, 7)))
                logger.exception('notification_delivery_failed', extra={'notification_id': item.pk})
            item.save()


@shared_task
def delete_old_checks():
    cutoff = timezone.now() - timedelta(days=30)
    # SET_NULL on incident references preserves durable incident history.
    while True:
        ids = list(CheckResult.objects.filter(checked_at__lt=cutoff).values_list('pk', flat=True)[:2000])
        if not ids:
            break
        CheckResult.objects.filter(pk__in=ids).delete()
    CheckJob.objects.filter(completed_at__lt=cutoff).delete()
