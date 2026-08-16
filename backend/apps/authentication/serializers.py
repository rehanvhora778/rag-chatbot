import re
import secrets

from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


def username_for_email(email):
    """
    Accounts are identified by email — Django still requires a unique username,
    so one is derived from the local part and de-duplicated with a numeric suffix.
    Users never see or type it.
    """
    base = re.sub(r'[^\w.@+-]', '', email.split('@')[0])[:120] or 'user'
    candidate = base
    n = 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f'{base}{n}'[:150]
    return candidate


class RegisterSerializer(serializers.Serializer):
    """
    Sign-up takes a name, an email and a password — no username field.

    Validation runs when the form is submitted, but the account is only created
    once the emailed code is verified. `pending_payload()` is what gets parked
    on the OTP record in the meantime — with the password already hashed, so a
    plaintext password never touches the database.
    """

    full_name = serializers.CharField(required=True, max_length=150)
    email     = serializers.EmailField(required=True)
    password  = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label='Confirm Password')

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return email

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return attrs

    def pending_payload(self):
        return {
            'full_name':     self.validated_data['full_name'].strip(),
            'email':         self.validated_data['email'],
            'password_hash': make_password(self.validated_data['password']),
        }


def create_user_from_pending(payload):
    """
    Turn a verified pending registration into a real account.

    The password arrives already hashed, so it is assigned straight to the field
    rather than going through `create_user`, which would hash it a second time.
    """
    email = payload['email'].strip().lower()
    user = User(
        username=username_for_email(email),
        email=email,
        first_name=(payload.get('full_name') or email.split('@')[0]).strip(),
    )
    user.password = payload['password_hash']
    user.save()
    return user


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='first_name', required=False, max_length=150)
    email     = serializers.EmailField(required=False)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'full_name', 'date_joined', 'last_login',
                  'is_staff', 'is_superuser')
        read_only_fields = ('id', 'username', 'date_joined', 'last_login',
                            'is_staff', 'is_superuser')

    def validate_email(self, value):
        # Email is the login identifier now, so it has to stay unique.
        email = value.strip().lower()
        others = User.objects.filter(email__iexact=email)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError('Another account already uses this email.')
        return email


class ChangePasswordSerializer(serializers.Serializer):
    old_password  = serializers.CharField(required=True, write_only=True)
    new_password  = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True, label='Confirm New Password')

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password': 'New passwords do not match.'})
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Final step of a forgotten-password reset — identity is proven by the ticket."""

    email         = serializers.EmailField(required=True)
    reset_token   = serializers.CharField(required=True, write_only=True)
    new_password  = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True, write_only=True, label='Confirm New Password')

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'New passwords do not match.'})
        return attrs


def get_or_create_google_user(email, full_name):
    """
    Look up (or create) the account behind a verified Google identity.

    Google-created accounts get an unusable random password: there is nothing to
    guess, and the owner can still set one later via the change-password flow.
    """
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    if user:
        created = False
        if full_name and not user.first_name:
            user.first_name = full_name
            user.save(update_fields=['first_name'])
    else:
        user = User.objects.create_user(
            username=username_for_email(email),
            email=email,
            first_name=(full_name or email.split('@')[0]).strip(),
            password=secrets.token_urlsafe(32),
        )
        created = True
    return user, created
