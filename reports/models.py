from django.db import models

class ReportExport(models.Model):
    workspace = models.ForeignKey('core.Workspace', on_delete=models.CASCADE)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    file = models.FileField(upload_to='reports/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'period_start'], name='one_weekly_report')]
