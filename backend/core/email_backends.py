"""
Email over HTTPS instead of SMTP.

Render's free instances have no outbound SMTP: connecting to smtp.gmail.com:587
fails with "[Errno 101] Network is unreachable" no matter how correct the Gmail
App Password is. Every OTP — sign-up and password reset — therefore failed in
production while working perfectly in local development.

Brevo's transactional endpoint is plain HTTPS, which is not blocked. This is a
normal Django email backend, so `send_mail()` in apps/authentication/otp.py
does not change; only EMAIL_BACKEND does.
"""
import json
import logging
from email.utils import parseaddr

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

_API_URL = 'https://api.brevo.com/v3/smtp/email'
_TIMEOUT = 15  # never hang a request on a slow provider


class BrevoAPIEmailBackend(BaseEmailBackend):
    """Send each message through Brevo's HTTP API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)

        from django.conf import settings

        self.api_key = getattr(settings, 'BREVO_API_KEY', '')
        self.default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', '')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError('BREVO_API_KEY is not set.')
            return 0

        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _payload(self, message):
        name, address = parseaddr(message.from_email or self.default_from)
        payload = {
            'sender': {'email': address},
            'to': [{'email': addr} for addr in message.to],
            'subject': message.subject,
            'textContent': message.body,
        }
        if name:
            payload['sender']['name'] = name
        if message.cc:
            payload['cc'] = [{'email': addr} for addr in message.cc]
        if message.bcc:
            payload['bcc'] = [{'email': addr} for addr in message.bcc]

        # An HTML alternative, when the caller attached one.
        for content, mimetype in getattr(message, 'alternatives', []):
            if mimetype == 'text/html':
                payload['htmlContent'] = content
                break

        return payload

    def _send(self, message):
        if not message.to:
            return False

        # Imported here rather than at module scope: this module is imported
        # during settings/app loading, and pulling the urllib3 stack in at that
        # point re-creates the startup import race that ensure_http_stack_loaded()
        # exists to prevent.
        import requests

        try:
            response = requests.post(
                _API_URL,
                headers={
                    'api-key': self.api_key,
                    'content-type': 'application/json',
                    'accept': 'application/json',
                },
                data=json.dumps(self._payload(message)),
                timeout=_TIMEOUT,
            )
        except Exception as exc:
            logger.error("Brevo request failed: %s", exc)
            if not self.fail_silently:
                raise
            return False

        if response.status_code >= 400:
            # Brevo puts the useful part in the body — an unverified sender or a
            # bad key both come back as 400/401 with a specific message.
            logger.error(
                "Brevo rejected the message (HTTP %s): %s",
                response.status_code, response.text[:500],
            )
            if not self.fail_silently:
                raise RuntimeError(
                    f'Brevo returned HTTP {response.status_code}: {response.text[:200]}'
                )
            return False

        return True
