"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from accounts.views import signup
from billing import views as billing
from monitors import views as monitors
from reports import views as reports
from core import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/signup/', signup, name='signup'),
    path('', monitors.dashboard, name='dashboard'),
    path('health/live', health.live),
    path('health/ready', health.ready),
    path('internal/metrics', health.metrics),
    path('infrastructure/', health.operations, name='operations'),
    path('billing/webhook/', billing.webhook),
    path('workspaces/<int:workspace_id>/billing/', billing.subscribe, name='subscribe'),
    path('workspaces/<int:workspace_id>/billing/checkout/', billing.checkout, name='checkout'),
    path('workspaces/<int:workspace_id>/billing/portal/', billing.portal, name='portal'),
    path('workspaces/<int:workspace_id>/monitors/new/', monitors.edit, name='monitor-create'),
    path('workspaces/<int:workspace_id>/monitors/<int:monitor_id>/', monitors.detail, name='monitor-detail'),
    path('workspaces/<int:workspace_id>/monitors/<int:monitor_id>/edit/', monitors.edit, name='monitor-edit'),
    path('workspaces/<int:workspace_id>/monitors/<int:monitor_id>/delete/', monitors.delete, name='monitor-delete'),
    path('workspaces/<int:workspace_id>/reports/', reports.reports, name='reports'),
    path('workspaces/<int:workspace_id>/reports/<int:report_id>/', reports.download, name='report-download'),
]
