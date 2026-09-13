import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.db import transaction
from .models import Incident, Monitor, Notification


def check_url(url, timeout):
    """Production uses a filtering egress proxy, including CONNECT destinations.

    Redirects are deliberately disabled. The proxy enforces resolved destination
    ACLs on actual connections, closing the DNS-rebinding gap of validation alone.
    """
    started = time.monotonic()
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or parts.username or parts.password or parts.port not in (None, 80, 443):
            raise ValueError('Invalid destination')
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Non-public destination')
        if settings.PRODUCTION and not settings.CHECK_PROXY:
            raise ValueError('Egress proxy required')
        with httpx.Client(proxy=settings.CHECK_PROXY or None, trust_env=False, timeout=timeout, follow_redirects=False) as client:
            with client.stream('GET', url, headers={'User-Agent': 'UptimeKit/1.0'}) as response:
                return dict(ok=response.status_code == 200, status_code=response.status_code,
                            latency_ms=int((time.monotonic() - started) * 1000))
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return dict(ok=False, error_message=type(exc).__name__, latency_ms=int((time.monotonic() - started) * 1000))


@transaction.atomic
def apply_check_result(result):
    monitor = Monitor.objects.select_for_update().get(pk=result.monitor_id)
    if monitor.last_checked_at and monitor.last_checked_at >= result.checked_at:
        return
    incident = Incident.objects.filter(monitor=monitor, ended_at__isnull=True).first()
    if not result.ok and incident is None:
        incident = Incident.objects.create(monitor=monitor, started_at=result.checked_at, opening_check=result)
        Notification.objects.get_or_create(incident=incident, kind='down')
    elif result.ok and incident is not None:
        incident.ended_at = result.checked_at
        incident.recovery_check = result
        incident.save(update_fields=['ended_at', 'recovery_check'])
        Notification.objects.get_or_create(incident=incident, kind='recovery')
    monitor.last_checked_at = result.checked_at
    monitor.last_ok = result.ok
    monitor.save(update_fields=['last_checked_at', 'last_ok'])
