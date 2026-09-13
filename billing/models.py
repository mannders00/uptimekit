from django.db import models
from .access import subscription_has_access

class BillingAccount(models.Model):
    workspace = models.OneToOneField('core.Workspace', on_delete=models.CASCADE, related_name='billing')
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    subscription_status = models.CharField(max_length=32, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)

    @property
    def has_access(self):
        return subscription_has_access(self.subscription_status)


class StripeEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
