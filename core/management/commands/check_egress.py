import json
import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Verify actual proxy destinations: public allowed, metadata/private/loopback denied.'

    def handle(self, *args, **options):
        if not settings.CHECK_PROXY:
            raise CommandError('CHECK_PROXY is required')
        with httpx.Client(proxy=settings.CHECK_PROXY, timeout=10, trust_env=False) as client:
            if client.get('https://example.com/').status_code != 200:
                raise CommandError('Public HTTPS failed')
            for url in ('http://169.254.169.254/latest/meta-data/', 'http://127.0.0.1/', 'http://10.0.0.1/', 'http://[::1]/'):
                if client.get(url).status_code != 403:
                    raise CommandError('Private destination was not denied')
            try:
                client.get('https://169.254.169.254/')
            except httpx.ProxyError:
                pass
            else:
                raise CommandError('Private HTTPS CONNECT was not denied')
        self.stdout.write(json.dumps({'egress_check': 'passed', 'public_https': True, 'private_http_and_connect_denied': True}))
