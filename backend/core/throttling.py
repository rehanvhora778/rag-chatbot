"""Rate limiting and brute-force protection for authentication.

Before this, the login endpoint had no limit of any kind. An `auth` throttle
scope was configured in settings and no view used it, which is the worst of both
worlds: it reads as protected in the settings file and is not.

**Two mechanisms, because they stop different attacks.**

*Per-IP throttling* limits how fast one source can try. It is the general
defence, and it is porous on its own: a distributed attempt spread across many
addresses stays under the limit at every one of them, while several legitimate
users behind one office NAT share a budget and lock each other out.

*Per-account lockout* limits how many times a single account can be guessed
at, regardless of where the attempts come from. That is the defence that
actually matters for credential stuffing, where the attacker has one password
and tries it against thousands of accounts — every attempt hits a different
account, so no account-level counter fires, but each *account* is also only
tried once, which is why the IP limit has to be there too.

Together: an attacker needs many addresses *and* many accounts, and gets a small
number of attempts at each.

**The lockout counts failures, not attempts**, and is cleared on success. A user
who mistypes twice and then gets it right starts from zero, so ordinary
fumbling never accumulates toward a lockout across a working day.

Counters live in the cache rather than the database. They are short-lived, and
writing a row per failed password attempt turns a brute-force attempt into a
database write amplification attack.
"""
import logging
from typing import Optional

from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger(__name__)

LOCKOUT_KEY = 'auth-failures:{identifier}'
MAX_FAILURES = 8
LOCKOUT_SECONDS = 900          # 15 minutes


class AuthRateThrottle(ScopedRateThrottle):
    """Per-IP throttle for authentication endpoints.

    Anonymous requests are keyed by address rather than by user, since there is
    no user yet — which is the whole point of the endpoint being attacked.
    """

    scope_attr = 'throttle_scope'

    def get_rate(self):
        """The configured rate, or None when there is none.

        DRF raises ImproperlyConfigured when a named scope has no rate, which
        turns a *missing configuration entry* into a 500 on the sign-in
        endpoint — the app stops working entirely because a rate limit was not
        set. Degrading to unlimited is the safer failure: the account lockout
        still applies, and a loud log line says the limit is off.
        """
        try:
            return super().get_rate()
        except Exception:
            logger.warning(
                'No throttle rate configured for the %r scope; per-IP rate '
                'limiting is OFF for this endpoint. Set it in '
                'REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].',
                getattr(self, 'scope', '?'),
            )
            return None

    def allow_request(self, request, view):
        # An unconfigured rate means no throttling rather than an exception.
        self.scope = getattr(view, self.scope_attr, None)
        if self.scope and self.get_rate() is None:
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        scope = getattr(view, self.scope_attr, None)
        if not scope:
            return None

        # Deliberately keyed on the address even for an authenticated request.
        # Someone already signed in has no reason to hammer the login endpoint,
        # and keying on their account would let one attacker with a valid
        # session get a fresh budget per account they hold.
        return self.cache_format % {
            'scope': scope,
            'ident': self.get_ident(request),
        }


def _key(identifier: str) -> str:
    return LOCKOUT_KEY.format(identifier=(identifier or '').strip().lower())


def is_locked_out(identifier: str) -> bool:
    """Has this account had too many recent failures?"""
    if not identifier:
        return False
    return (cache.get(_key(identifier)) or 0) >= MAX_FAILURES


def record_failure(identifier: str) -> int:
    """Count one failed sign-in. Returns the new failure count."""
    if not identifier:
        return 0

    key = _key(identifier)
    # add() only sets the key if it is absent, which is what starts the window;
    # incr() then bumps it without extending the expiry. Together they give a
    # fixed window from the first failure rather than one that a persistent
    # attacker can keep alive indefinitely by continuing to guess.
    cache.add(key, 0, LOCKOUT_SECONDS)
    try:
        count = cache.incr(key)
    except ValueError:
        # The key expired between add() and incr().
        cache.set(key, 1, LOCKOUT_SECONDS)
        count = 1

    if count == MAX_FAILURES:
        logger.warning(
            'Account %r locked for %d seconds after %d failed sign-in attempts.',
            identifier, LOCKOUT_SECONDS, count,
        )
    return count


def clear_failures(identifier: str) -> None:
    """Forget the failures for an account. Called on a successful sign-in."""
    if identifier:
        cache.delete(_key(identifier))


def lockout_message(identifier: str) -> Optional[str]:
    """The message to show a locked-out account, or None.

    Says that the account is temporarily locked without confirming whether it
    exists. A message that appeared only for real accounts would turn the
    lockout into an account-enumeration oracle — exactly the information the
    generic "invalid credentials" response is designed to withhold.
    """
    if not is_locked_out(identifier):
        return None
    minutes = max(1, LOCKOUT_SECONDS // 60)
    return (
        f'Too many failed sign-in attempts. Try again in about {minutes} minutes, '
        'or reset your password.'
    )


