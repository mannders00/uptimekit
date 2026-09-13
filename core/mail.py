import logging
from django.core.mail.backends.base import BaseEmailBackend


class DisabledEmailBackend(BaseEmailBackend):
    """Explicit no-email deployment mode; never print reset tokens or message bodies."""
    def send_messages(self, email_messages):
        logging.getLogger(__name__).warning('email_disabled_no_messages_delivered')
        return 0
