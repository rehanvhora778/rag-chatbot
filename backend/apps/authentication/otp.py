"""
One-time codes for sign-up verification and password reset.

Codes live in MongoDB rather than SQLite so this app needs no migration, and a
TTL index on `purge_at` lets Mongo delete spent records without a cleanup job.
Nothing sensitive is stored in the clear: the code itself and the reset ticket
are kept as salted hashes, and a pending registration keeps only the *hashed*
password until the account is actually created.

One document per (email, purpose) — issuing a new code overwrites the old one,
so a code is only ever valid until the next send.
"""
import logging
import secrets
from datetime import UTC, timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone
from pymongo import ASCENDING, ReturnDocument

from core.mongo import otps_col

logger = logging.getLogger(__name__)

PURPOSE_REGISTER = 'register'
PURPOSE_RESET    = 'password_reset'

# Wrong code, expired code, too many tries — every failure the caller may hit.
class OTPError(Exception):
    """Carries a user-facing message and the HTTP status it should map to."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


_indexes_ready = False


def _ensure_indexes():
    """
    `core.mongo.create_indexes()` is not run at startup anywhere, so the two
    indexes this module depends on are created on first use instead: uniqueness
    keeps one live code per email per flow, and the TTL sweeps spent records.
    Failure is logged, not raised — index upkeep must never block a sign-up.
    """
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        otps_col().create_index([('email', ASCENDING), ('purpose', ASCENDING)], unique=True)
        otps_col().create_index([('purge_at', ASCENDING)], expireAfterSeconds=0)
    except Exception as exc:
        logger.warning("Could not ensure OTP indexes: %s", exc)
    _indexes_ready = True


def _now():
    return timezone.now()


def _aware(value):
    """
    BSON has no timezone, so datetimes come back from Mongo naive (but always
    UTC). Django's `now()` is UTC-aware, and comparing the two raises — so every
    stored timestamp is put back on the aware side before it is used.
    """
    if value is None:
        return None
    return timezone.make_aware(value, UTC) if timezone.is_naive(value) else value


def _generate_code() -> str:
    """A zero-padded numeric code — `secrets`, not `random`, so it is unguessable."""
    upper = 10 ** settings.OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(settings.OTP_LENGTH)


def _subject_and_body(code: str, purpose: str, name: str = '') -> tuple:
    minutes = settings.OTP_TTL_MINUTES
    greeting = f"Hi {name}," if name else "Hi,"

    if purpose == PURPOSE_REGISTER:
        return (
            'Your RAG Chatbot verification code',
            f"{greeting}\n\n"
            f"Your verification code is {code}\n\n"
            f"Enter it on the sign-up page to finish creating your account. "
            f"The code expires in {minutes} minutes.\n\n"
            f"If you did not try to sign up, you can ignore this email — no "
            f"account has been created.\n\n"
            f"— RAG Chatbot"
        )

    return (
        'Your RAG Chatbot password reset code',
        f"{greeting}\n\n"
        f"Your password reset code is {code}\n\n"
        f"Enter it on the reset page to choose a new password. "
        f"The code expires in {minutes} minutes.\n\n"
        f"If you did not ask to reset your password, ignore this email — your "
        f"current password still works.\n\n"
        f"— RAG Chatbot"
    )


def _send(email: str, code: str, purpose: str, name: str = '') -> None:
    """
    Mail the code. With no mail transport configured Django's console backend
    prints it to the server log, which keeps the flow usable offline — and on
    Render's free tier, where outbound SMTP is blocked outright.
    """
    subject, body = _subject_and_body(code, purpose, name)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    except Exception as exc:
        logger.error("Could not send %s code to %s: %s", purpose, email, exc)
        raise OTPError(
            'Could not send the verification email. Check the mail settings in backend/.env '
            'and try again.',
            status_code=503,
        ) from exc

    # The console backend has already dumped the whole message to the log, so
    # this repeats nothing that is not there — it just makes the code greppable
    # instead of buried in a full RFC-822 dump. Only ever runs when no real
    # transport is configured; with SMTP or an API backend nothing is logged.
    if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
        logger.info("OTP (%s) for %s: %s", purpose, email, code)


def _check_rate_limits(record) -> None:
    """Guards against someone hammering the send endpoint (or a user's inbox)."""
    if record is None:
        return

    now = _now()

    last_sent = _aware(record.get('last_sent_at'))
    if last_sent:
        elapsed = (now - last_sent).total_seconds()
        cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
        if elapsed < cooldown:
            wait = int(cooldown - elapsed) or 1
            raise OTPError(f'Please wait {wait} more second{"s" if wait != 1 else ""} '
                           f'before asking for another code.', status_code=429)

    window_start = _aware(record.get('window_started_at'))
    sends = record.get('send_count', 0)
    if window_start and (now - window_start) < timedelta(hours=1):
        if sends >= settings.OTP_MAX_SENDS_PER_HOUR:
            raise OTPError('Too many codes requested for this email. Try again in an hour.',
                           status_code=429)


def issue(email: str, purpose: str, payload: dict = None, name: str = '') -> dict:
    """
    Generate, store and email a fresh code. Returns metadata for the response.
    Raises OTPError when rate-limited or when the mail could not be sent.
    """
    _ensure_indexes()
    email = email.strip().lower()
    col = otps_col()
    existing = col.find_one({'email': email, 'purpose': purpose})

    _check_rate_limits(existing)

    now = _now()
    code = _generate_code()

    # Keep counting within the existing hour window; start a new one otherwise.
    window_start = _aware(existing.get('window_started_at')) if existing else None
    send_count = existing.get('send_count', 0) if existing else 0
    if not window_start or (now - window_start) >= timedelta(hours=1):
        window_start = now
        send_count = 0

    doc = {
        'email':             email,
        'purpose':           purpose,
        'code_hash':         make_password(code),
        'expires_at':        now + timedelta(minutes=settings.OTP_TTL_MINUTES),
        'attempts':          0,
        'last_sent_at':      now,
        'send_count':        send_count + 1,
        'window_started_at': window_start,
        # Outlive the code itself so the rate-limit counters survive expiry.
        'purge_at':          now + timedelta(hours=2),
        'created_at':        now,
        'payload':           payload or (existing or {}).get('payload') or {},
        # A new code invalidates any ticket handed out for an older one.
        'reset_token_hash':  None,
        'reset_expires_at':  None,
    }

    col.update_one({'email': email, 'purpose': purpose}, {'$set': doc}, upsert=True)

    # Mail last: a delivery failure must not leave a code the user never saw.
    _send(email, code, purpose, name or (payload or {}).get('full_name', ''))

    logger.info("Issued %s code to %s (send #%s)", purpose, email, doc['send_count'])
    return {
        'email': email,
        'expires_in_seconds': settings.OTP_TTL_MINUTES * 60,
        'resend_after_seconds': settings.OTP_RESEND_COOLDOWN_SECONDS,
    }


def verify(email: str, code: str, purpose: str) -> dict:
    """
    Check a code and return its record. The record is NOT deleted — callers
    finish the flow (create the account / set the password) and then call
    `consume()`, so a crash in between doesn't strand the user without a code.
    """
    email = email.strip().lower()
    code = str(code or '').strip()
    col = otps_col()

    record = col.find_one({'email': email, 'purpose': purpose})
    if record is None:
        raise OTPError('No verification code is pending for this email. Request a new one.')

    if _aware(record['expires_at']) < _now():
        raise OTPError('That code has expired. Request a new one.')

    if record.get('attempts', 0) >= settings.OTP_MAX_ATTEMPTS:
        raise OTPError('Too many incorrect attempts. Request a new code.', status_code=429)

    if not code.isdigit() or len(code) != settings.OTP_LENGTH:
        col.update_one({'_id': record['_id']}, {'$inc': {'attempts': 1}})
        raise OTPError(f'Enter the {settings.OTP_LENGTH}-digit code from your email.')

    if not check_password(code, record['code_hash']):
        updated = col.find_one_and_update(
            {'_id': record['_id']}, {'$inc': {'attempts': 1}},
            return_document=ReturnDocument.AFTER,
        )
        left = max(settings.OTP_MAX_ATTEMPTS - (updated or {}).get('attempts', 0), 0)
        if left:
            raise OTPError(f'That code is not correct. {left} attempt{"s" if left != 1 else ""} left.')
        raise OTPError('That code is not correct. Request a new code.', status_code=429)

    return record


def consume(email: str, purpose: str) -> None:
    """Delete the record once the flow it guards has completed."""
    otps_col().delete_one({'email': email.strip().lower(), 'purpose': purpose})


def issue_reset_ticket(email: str) -> str:
    """
    Swap a verified reset code for a single-use ticket, so the final request
    carries the new password without re-sending the code alongside it.
    """
    email = email.strip().lower()
    token = secrets.token_urlsafe(32)
    otps_col().update_one(
        {'email': email, 'purpose': PURPOSE_RESET},
        {'$set': {
            'reset_token_hash': make_password(token),
            'reset_expires_at': _now() + timedelta(minutes=settings.OTP_RESET_TOKEN_TTL_MINUTES),
            # The code has done its job; stop it being replayed.
            'code_hash': make_password(secrets.token_urlsafe(16)),
        }},
    )
    return token


def check_reset_ticket(email: str, token: str) -> dict:
    email = email.strip().lower()
    record = otps_col().find_one({'email': email, 'purpose': PURPOSE_RESET})

    if record is None or not record.get('reset_token_hash'):
        raise OTPError('This reset session is no longer valid. Start again.')

    expires = _aware(record.get('reset_expires_at'))
    if not expires or expires < _now():
        raise OTPError('This reset session has expired. Start again.')

    if not token or not check_password(token, record['reset_token_hash']):
        raise OTPError('This reset session is no longer valid. Start again.', status_code=401)

    return record
