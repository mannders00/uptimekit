from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from core.services import workspace_for
from .models import ReportExport


@login_required
def reports(request, workspace_id):
    workspace = workspace_for(request.user, workspace_id)
    return render(request, 'reports.html', {'workspace': workspace, 'reports': ReportExport.objects.filter(workspace=workspace).order_by('-period_start')[:52]})


@login_required
def download(request, workspace_id, report_id):
    workspace = workspace_for(request.user, workspace_id)
    report = get_object_or_404(ReportExport, workspace=workspace, pk=report_id)
    return FileResponse(report.file.open('rb'), as_attachment=True, filename=f'uptime-{report.period_start.date()}.csv')
