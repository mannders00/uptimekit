import json
import time
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.utils import timezone
from accounts.models import User
from core.models import Heartbeat, Membership, Workspace
from monitors.models import CheckResult, Monitor


class Command(BaseCommand):
    help = 'Exercise authenticated dashboard, database and a new scheduler/worker canary result.'

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=150)

    def handle(self, *args, **options):
        started = timezone.now()
        client = Client(HTTP_HOST='localhost')
        if client.get('/accounts/login/', secure=True).status_code != 200:
            raise CommandError('Login page failed')
        # No persistent credentials or paid entitlement; temporary login exercises auth.
        user = User.objects.create_user(username=f'smoke-{time.time_ns()}', email=f'smoke-{time.time_ns()}@example.invalid')
        workspace = Workspace.objects.create(name='Disposable release smoke')
        try:
            Membership.objects.create(user=user, workspace=workspace)
            from billing.models import BillingAccount
            BillingAccount.objects.create(workspace=workspace)
            client.force_login(user)
            response = client.get('/', secure=True)
            if response.status_code != 200 or workspace.name.encode() not in response.content:
                raise CommandError('Authenticated tenant dashboard failed')
        finally:
            client.logout()
            workspace.delete()
            user.delete()
        deadline = time.monotonic() + options['timeout']
        while time.monotonic() < deadline:
            result = CheckResult.objects.filter(monitor__is_canary=True, ok=True, checked_at__gte=started).first()
            dispatcher = Heartbeat.objects.filter(name='dispatcher', updated_at__gte=started).exists()
            if result and dispatcher:
                self.stdout.write(json.dumps({'runtime_check': 'passed', 'canary_check_id': result.pk, 'latency_ms': result.latency_ms, 'completed_at': timezone.now().isoformat()}))
                return
            time.sleep(3)
        raise CommandError('No fresh successful canary through scheduler → Redis → worker → PostgreSQL')
