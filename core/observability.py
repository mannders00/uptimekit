import json
import logging
import time
from prometheus_client import Counter, Histogram

REQUESTS = Counter('uptimekit_http_requests_total', 'HTTP requests', ['route', 'status'])
LATENCY = Histogram('uptimekit_http_duration_seconds', 'Request duration', ['route'])
WEBHOOK_FAILURES = Counter('uptimekit_webhook_failures_total', 'Rejected/failed webhooks', ['reason'])


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {'timestamp': self.formatTime(record), 'level': record.levelname, 'logger': record.name, 'message': record.getMessage()}
        for key in ('monitor_id', 'check_id', 'ok', 'latency_ms', 'notification_id', 'billing_account_id'):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data['exception'] = self.formatException(record.exc_info)
        return json.dumps(data)


class RequestMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        route = request.resolver_match.route if request.resolver_match else 'unmatched'
        REQUESTS.labels(route, str(response.status_code)).inc()
        LATENCY.labels(route).observe(time.monotonic() - started)
        return response
