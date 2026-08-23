"""Per-user state that ``django.contrib.auth.User`` does not already hold."""
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import TimeStampedModel


class Role(models.TextChoices):
    USER = 'user', 'User'
    ADMIN = 'admin', 'Admin'
    SUPERADMIN = 'superadmin', 'Superadmin'


class UserProfile(TimeStampedModel):
    """Extra fields for an account, keyed one-to-one on the auth user.

    Note what is deliberately *not* here: a ``role`` column. Django already
    stores the authority a user has, in ``is_staff`` and ``is_superuser``, and
    those are the flags the admin site, the permission classes and every
    third-party package actually consult. A second stored copy would be a
    second source of truth that has to be kept in step, and the failure mode
    when it drifts is someone keeping admin access after being demoted.
    ``role`` below is therefore derived, not stored.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='profile',
    )

    # The OTP sign-up flow proves an address before activating the account.
    # Recording it explicitly separates "has confirmed their email" from
    # "is_active", which an admin may also toggle for unrelated reasons.
    email_verified = models.BooleanField(default=False)

    # Per-account override of MAX_DOCUMENTS_PER_USER. Null means "use the
    # global setting"; 0 means this account may not upload at all.
    document_quota = models.IntegerField(null=True, blank=True)

    last_active_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'user profile'

    def __str__(self):
        return f'Profile for {self.user.get_username()}'

    @property
    def role(self) -> str:
        if self.user.is_superuser:
            return Role.SUPERADMIN
        if self.user.is_staff:
            return Role.ADMIN
        return Role.USER

    @property
    def effective_document_quota(self) -> int:
        from django.conf import settings as django_settings

        if self.document_quota is not None:
            return self.document_quota
        return django_settings.MAX_DOCUMENTS_PER_USER


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    """Give every account a profile the moment it exists.

    Without this, any code path that creates a user — the OTP sign-up, Google
    sign-in, ``createsuperuser``, a test factory — has to remember to create the
    profile too, and the one that forgets raises RelatedObjectDoesNotExist at
    some unrelated point later.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
