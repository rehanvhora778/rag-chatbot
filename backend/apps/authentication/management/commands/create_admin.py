"""
Create (or repair) the built-in administrator account.

    python manage.py create_admin

Re-running is safe: an existing account with the same email is promoted to
staff + superuser, re-activated, and its password reset to the configured one.
Override any value with a flag or via DEFAULT_ADMIN_* in backend/.env.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from apps.authentication.serializers import username_for_email


class Command(BaseCommand):
    help = 'Create or update the default administrator account.'

    def add_arguments(self, parser):
        parser.add_argument('--email',    default=settings.DEFAULT_ADMIN_EMAIL)
        parser.add_argument('--password', default=settings.DEFAULT_ADMIN_PASSWORD)
        parser.add_argument('--name',     default=settings.DEFAULT_ADMIN_NAME)

    def handle(self, *args, **options):
        email    = options['email'].strip().lower()
        password = options['password']
        name     = options['name'].strip()

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
        self.stdout.write('Sign in at /admin-login with this email and password.')
