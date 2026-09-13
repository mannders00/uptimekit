from django.contrib import admin

from .models import Monitor, CheckResult, Incident, Notification, CheckJob


@admin.register(Monitor)
class MonitorAdmin(admin.ModelAdmin):
    list_display = ['name', 'workspace', 'enabled', 'last_ok', 'last_checked_at']
    search_fields = ['name', 'url']
    list_filter = ['enabled', 'is_canary']


admin.site.register([CheckResult, Incident, Notification, CheckJob])
