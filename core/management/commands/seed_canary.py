from django.core.management.base import BaseCommand
from django.db import transaction
from billing.models import BillingAccount
from core.models import Workspace
from monitors.models import Monitor


class Command(BaseCommand):
    help = 'Create the operator-owned synthetic workspace, without a customer login or billing identity.'

    @transaction.atomic
    def handle(self, *args, **options):
        # Identified through a canary monitor, never an untrusted workspace name.
        monitor = Monitor.objects.filter(is_canary=True).first()
        if monitor:
            self.stdout.write(str(monitor.pk))
            return
        workspace = Workspace.objects.create(name='Infrastructure canary (operator-owned)')
        BillingAccount.objects.create(workspace=workspace, subscription_status='active')
        monitor = Monitor.objects.create(workspace=workspace, name='Public Internet canary', url='https://example.com/', is_canary=True, interval_seconds=30)
        self.stdout.write(str(monitor.pk))
