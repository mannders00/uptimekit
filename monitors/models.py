from django.db import models

from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone


class Monitor(models.Model):
    workspace = models.ForeignKey('core.Workspace', on_delete=models.CASCADE, related_name='monitors')
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    interval_seconds = models.PositiveIntegerField(default=60, choices=[(v, f'{v} seconds') for v in (30, 60, 300, 900)])
    timeout_seconds = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(10)])
    enabled = models.BooleanField(default=True)
    is_canary = models.BooleanField(default=False)
    next_check_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CheckJob(models.Model):
    """Durable scheduling outbox; broker loss is repaired on the next dispatch."""
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['monitor'], condition=models.Q(completed_at__isnull=True), name='one_pending_check')]


class CheckResult(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name='checks')
    job = models.OneToOneField(CheckJob, on_delete=models.SET_NULL, null=True)
    checked_at = models.DateTimeField(default=timezone.now)
    ok = models.BooleanField()
    status_code = models.PositiveIntegerField(null=True)
    latency_ms = models.PositiveIntegerField(null=True)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=['monitor', '-checked_at'])]


class Incident(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name='incidents')
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    opening_check = models.ForeignKey(CheckResult, on_delete=models.SET_NULL, null=True, related_name='+')
    recovery_check = models.ForeignKey(CheckResult, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['monitor'], condition=models.Q(ended_at__isnull=True), name='one_open_incident')]


class Notification(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['incident', 'kind'], name='one_notification_per_transition')]
