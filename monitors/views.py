from django.contrib.auth.decorators import login_required
from django.conf import settings
from billing.access import workspace_has_access
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from core.models import Workspace
from core.services import workspace_for
from .forms import MonitorForm


@login_required
def dashboard(request):
    return render(request, 'dashboard.html', {'workspaces': Workspace.objects.filter(memberships__user=request.user).select_related('billing').prefetch_related('monitors'), 'billing_enabled': settings.BILLING_ENABLED})


@login_required
def edit(request, workspace_id, monitor_id=None):
    workspace = workspace_for(request.user, workspace_id)
    if not workspace_has_access(workspace):
        return redirect('subscribe', workspace_id=workspace_id)
    instance = get_object_or_404(workspace.monitors, pk=monitor_id) if monitor_id else None
    form = MonitorForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        monitor = form.save(commit=False)
        monitor.workspace = workspace
        monitor.save()
        return redirect('dashboard')
    return render(request, 'form.html', {'form': form, 'title': 'Configure monitor'})


@login_required
def detail(request, workspace_id, monitor_id):
    workspace = workspace_for(request.user, workspace_id)
    monitor = get_object_or_404(workspace.monitors, pk=monitor_id)
    return render(request, 'monitor.html', {'monitor': monitor, 'checks': monitor.checks.order_by('-checked_at')[:100], 'incidents': monitor.incidents.order_by('-started_at')[:20]})


@login_required
@require_POST
def delete(request, workspace_id, monitor_id):
    workspace = workspace_for(request.user, workspace_id)
    get_object_or_404(workspace.monitors, pk=monitor_id).delete()
    return redirect('dashboard')
