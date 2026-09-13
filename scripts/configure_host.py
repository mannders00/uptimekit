"""Idempotent first-boot configuration. Secrets never go to stdout."""
import os
from pathlib import Path
import pwd
import secrets

root = Path('/etc/uptimekit')
owner = pwd.getpwnam('admin')


def write_once(path, content, mode=0o600):
    if not path.exists():
        path.write_text(content)
        path.chmod(mode)
        os.chown(path, owner.pw_uid, owner.pw_gid)


write_once(root / 'metrics-token', secrets.token_hex(32), 0o644)
write_once(root / 'grafana-password', secrets.token_hex(24), 0o644)
token = (root / 'metrics-token').read_text().strip()
for environment, port in [('dev', 8001), ('prod', 8002)]:
    values = {
        'ENVIRONMENT': environment, 'WEB_PORT': port,
        'DJANGO_ENV': 'production', 'DJANGO_DEBUG': 'false',
        'DJANGO_SECRET_KEY': secrets.token_hex(48),
        'DJANGO_ALLOWED_HOSTS': 'uptimekit.masoftware.net,localhost,127.0.0.1,web,dev-web,prod-web',
        'SITE_URL': 'https://uptimekit.masoftware.net',
        'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://uptimekit.masoftware.net',
        'POSTGRES_HOST': 'db', 'POSTGRES_DB': 'uptimekit', 'POSTGRES_USER': 'uptimekit',
        'POSTGRES_PASSWORD': secrets.token_hex(24), 'REDIS_URL': 'redis://redis:6379/0',
        'CHECK_PROXY': 'http://check-proxy:3128', 'OPS_TOKEN': token,
        'EMAIL_BACKEND': 'core.mail.DisabledEmailBackend',
        'AWS_DEFAULT_REGION': 'us-east-2',
    }
    write_once(root / f'{environment}.env', ''.join(f'{k}={v}\n' for k, v in values.items()))
write_once(root / 'backup.env', 'BACKUP_BUCKET=\nAWS_DEFAULT_REGION=us-east-2\n')
write_once(root / 'reticle.env', f'RETICLE_VIEW_TOKEN={secrets.token_hex(32)}\n')
