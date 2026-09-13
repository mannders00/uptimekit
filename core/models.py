from django.db import models

from django.conf import settings


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=[('owner', 'Owner'), ('member', 'Member')], default='owner')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')]


class Heartbeat(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    updated_at = models.DateTimeField(auto_now=True)
