import csv
from datetime import timedelta
from io import StringIO
from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from core.models import Workspace
from .models import ReportExport


@shared_task
def generate_reports():
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = today - timedelta(days=today.weekday())
    start = end - timedelta(days=7)
    for pk in Workspace.objects.filter(billing__subscription_status='active').values_list('pk', flat=True):
        with transaction.atomic():
            workspace = Workspace.objects.select_for_update().get(pk=pk)
            if not workspace.billing.has_access:
                continue
            export, _ = ReportExport.objects.get_or_create(workspace=workspace, period_start=start, defaults={'period_end': end})
            if export.file:
                continue
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(['monitor', 'checks', 'failed_checks', 'sample_success_percent'])
            for monitor in workspace.monitors.all():
                stats = monitor.checks.filter(checked_at__gte=start, checked_at__lt=end).aggregate(total=Count('id'), failed=Count('id', filter=Q(ok=False)))
                name = monitor.name
                if name.startswith(('=', '+', '-', '@', '\t', '\r')):
                    name = "'" + name
                writer.writerow([name, stats['total'], stats['failed'], round(100 * (1 - stats['failed'] / stats['total']), 3) if stats['total'] else ''])
            export.file.save(f'{pk}-{start.date()}.csv', ContentFile(buf.getvalue().encode()))
