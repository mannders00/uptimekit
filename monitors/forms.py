from urllib.parse import urlsplit
import ipaddress
from django import forms
from .models import Monitor


class MonitorForm(forms.ModelForm):
    class Meta:
        model = Monitor
        fields = ['name', 'url', 'interval_seconds', 'timeout_seconds', 'enabled']

    def clean_url(self):
        url = self.cleaned_data['url']
        parts = urlsplit(url)
        try:
            if parts.scheme not in ('http', 'https') or parts.username or parts.password or parts.port not in (None, 80, 443):
                raise ValueError()
            host = parts.hostname
            if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
                raise ValueError()
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                ip = None
            if ip is not None and not ip.is_global:
                raise ValueError()
        except (ValueError, AttributeError):
            raise forms.ValidationError('Use a public HTTP(S) URL on port 80 or 443 without credentials.')
        return url
