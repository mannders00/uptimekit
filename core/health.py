import logging
import secrets
from datetime import timedelta
import httpx
import redis
from django.conf import settings
from django.db import connection
from django.db.models import Min, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from billing.models import BillingAccount
from monitors.models import CheckJob, CheckResult, Monitor, Notification
from .models import Heartbeat


def live(request):
    return JsonResponse({'status': 'ok'})


def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return JsonResponse({'status': 'ok', 'release': settings.RELEASE_SHA})
    except Exception:
        logging.getLogger(__name__).exception('database_not_ready')
        return JsonResponse({'status': 'not-ready'}, status=503)


def metrics(request):
    if not settings.OPS_TOKEN or not secrets.compare_digest(request.headers.get('Authorization', ''), f'Bearer {settings.OPS_TOKEN}'):
        return HttpResponse(status=403)
    now = timezone.now()
    values = {}
    try:
        broker = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2, socket_connect_timeout=2)
        values['redis_up'] = int(broker.ping())
        values['queue_depth'] = broker.llen('celery')
    except redis.RedisError:
        values['redis_up'] = 0
    try:
        values['database_up'] = 1
        for name in ('dispatcher', 'worker'):
            beat = Heartbeat.objects.filter(name=name).first()
            values[f'{name}_age_seconds'] = (now - beat.updated_at).total_seconds() if beat else 1e9
        canary = CheckResult.objects.filter(monitor__is_canary=True, ok=True).aggregate(last=Max('checked_at'))['last']
        values['canary_age_seconds'] = (now - canary).total_seconds() if canary else 1e9
        oldest = CheckJob.objects.filter(completed_at=None).aggregate(oldest=Min('created_at'))['oldest']
        values['oldest_pending_seconds'] = (now - oldest).total_seconds() if oldest else 0
        values['pending_jobs'] = CheckJob.objects.filter(completed_at=None).count()
        values['stale_monitors'] = Monitor.objects.filter(enabled=True, workspace__billing__subscription_status='active', next_check_at__lt=now-timedelta(minutes=2)).count()
        values['notification_pending'] = Notification.objects.filter(delivered_at=None).count()
        values['notification_failed'] = Notification.objects.filter(delivered_at=None, attempts__gt=0).count()
        values['billing_stale'] = BillingAccount.objects.exclude(stripe_customer_id='').filter(reconciled_at__lt=now-timedelta(hours=1)).count()
    except Exception:
        values['database_up'] = 0
    body = generate_latest().decode() + ''.join(f'# TYPE uptimekit_{key} gauge\nuptimekit_{key} {value}\n' for key, value in values.items())
    return HttpResponse(body, content_type=CONTENT_TYPE_LATEST)


def operations(request):
    alerts, available = [], False
    try:
        response = httpx.get('http://alertmanager:9093/api/v2/alerts', timeout=2, trust_env=False)
        response.raise_for_status()
        # Only curated fields; no internal hostnames, arbitrary labels or tenant data.
        alerts = [{'name': a['labels'].get('alertname', 'Infrastructure alert'), 'severity': a['labels'].get('severity', 'warning'), 'since': a['startsAt']} for a in response.json()]
        available = True
    except (httpx.HTTPError, ValueError):
        pass
    return render(request, 'operations.html', {'alerts': alerts, 'available': available, 'release': settings.RELEASE_SHA, 'sampled_at': timezone.now()})
