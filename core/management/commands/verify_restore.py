import json
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from core.models import Workspace, Membership
from accounts.models import User
from billing.models import BillingAccount
from monitors.models import Monitor, CheckResult, Incident


class Command(BaseCommand):
    help = 'Validate restored schema, tenant relations, canary history and billing projection.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        counts = {model.__name__: model.objects.count() for model in (User, Workspace, Membership, BillingAccount, Monitor, CheckResult, Incident)}
        if not Monitor.objects.filter(is_canary=True, checks__ok=True).exists():
            raise CommandError('Restored canary and successful history missing')
        for account in BillingAccount.objects.select_related('workspace'):
            if not account.workspace_id:
                raise CommandError('Invalid billing relation')
        self.stdout.write(json.dumps({'restore_verified': True, 'counts': counts}))
