"""
Create (or repair) the built-in administrator account.

    python manage.py create_admin --password '<strong-password>'
    python manage.py create_admin --generate-password

Re-running is safe: an existing account with the same email is promoted to
staff + superuser, re-activated, and its password reset to the one given.
Override any value with a flag or via DEFAULT_ADMIN_* in backend/.env.

There is deliberately no default password. Shipping one in the repository means
every clone of this project has an administrator account whose password anyone
who read the source can type, and seed credentials are exactly the kind of thing
that survives all the way into a deployment.
"""

import secrets
import string

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.authentication.serializers import username_for_email

# Ambiguous glyphs are left out so a generated password can be read off a
# terminal and typed into a login form without a "was that l or 1?" moment.
_ALPHABET = (
    string.ascii_lowercase.replace('l', '')
    + string.ascii_uppercase.replace('I', '').replace('O', '')
    + string.digits.replace('0', '').replace('1', '')
    + '!@#$%^&*-_=+'
)


def generate_password(length: int = 20) -> str:
    return ''.join(secrets.choice(_ALPHABET) for _ in range(length))


class Command(BaseCommand):
    help = 'Create or update the default administrator account.'

    def add_arguments(self, parser):
        parser.add_argument('--email',    default=settings.DEFAULT_ADMIN_EMAIL)
        parser.add_argument('--password', default=settings.DEFAULT_ADMIN_PASSWORD)
        parser.add_argument('--name',     default=settings.DEFAULT_ADMIN_NAME)
        parser.add_argument(
            '--generate-password',
            action='store_true',
            help='Generate a strong random password and print it once.',
        )
        parser.add_argument(
            '--skip-if-unset',
            action='store_true',
            help='Exit quietly instead of failing when no password is configured. '
                 'For deploy scripts that run this unconditionally.',
        )

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        name = options['name'].strip()
        password = options['password']
        generated = False

        if options['generate_password']:
            password = generate_password()
            generated = True
        elif not password:
            if options['skip_if_unset']:
                self.stdout.write(self.style.WARNING(
                    'No admin password configured — skipping. Set DEFAULT_ADMIN_PASSWORD '
                    'or run: manage.py create_admin --generate-password'
                ))
                return
            raise CommandError(
                'No password given.\n'
                '  Set DEFAULT_ADMIN_PASSWORD in backend/.env,\n'
                '  pass --password "<strong-password>",\n'
                '  or run with --generate-password to have one generated for you.'
            )

        # A seeded superuser is the single most valuable account in the system,
        # so it is held to the same password rules as anyone signing up.
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                'That administrator password is too weak:\n  - '
                + '\n  - '.join(exc.messages)
            ) from exc

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                username=username_for_email(email),
                email=email,
                first_name=name,
                password=password,
            )
            action = 'Created'
        else:
            user.set_password(password)
            user.first_name = name or user.first_name
            action = 'Updated'

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f'{action} administrator: {email} (username "{user.username}", id {user.id})'
        ))
        if generated:
            self.stdout.write(self.style.WARNING(
                f'\n  Generated password: {password}\n'
                '  This is shown once and is not stored anywhere else. Save it now.\n'
            ))
        self.stdout.write('Sign in at /admin-login with this email and password.')
