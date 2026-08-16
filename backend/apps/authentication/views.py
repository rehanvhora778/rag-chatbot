import logging

from django.conf import settings
from django.contrib.auth.models import User, update_last_login
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

from core.responses import APIResponse
from core.mongo import analytics_col, otps_col
from core.constants import EVENT_LOGIN
from . import otp
from .serializers import (
    RegisterSerializer, UserProfileSerializer, ChangePasswordSerializer,
    PasswordResetConfirmSerializer, create_user_from_pending,
    get_or_create_google_user,
)

logger = logging.getLogger(__name__)


def _session_payload(user):
    """Tokens + profile — the shape every sign-in route returns."""
    refresh = RefreshToken.for_user(user)
    return {
        'user': UserProfileSerializer(user).data,
        'tokens': {'access': str(refresh.access_token), 'refresh': str(refresh)},
    }


def _record_login(user, method):
    # Our custom login flow bypasses Django's automatic last_login update.
    update_last_login(None, user)
    try:
        analytics_col().insert_one({
            'user_id': user.id,
            'event_type': EVENT_LOGIN,
            'metadata': {'email': user.email, 'method': method},
            'created_at': timezone.now(),
        })
    except Exception:
        pass


class RegisterView(APIView):
    """
    Step 1 of sign-up: validate the form and email a code.

    No account exists yet — the details are parked on the OTP record (with the
    password already hashed) and only become a user once the code is verified,
    so an abandoned sign-up leaves nothing behind.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Registration failed.', serializer.errors)

        payload = serializer.pending_payload()
        try:
            meta = otp.issue(payload['email'], otp.PURPOSE_REGISTER,
                             payload=payload, name=payload['full_name'])
        except otp.OTPError as exc:
            return APIResponse.error(exc.message, status_code=exc.status_code)

        logger.info("Sign-up code sent to %s", payload['email'])
        return APIResponse.success(data=meta,
                                   message='We sent a verification code to your email.')


class RegisterResendView(APIView):
    """Re-issues the sign-up code for a pending registration."""

    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        if not email:
            return APIResponse.error('Email is required.')

        record = otps_col().find_one({'email': email, 'purpose': otp.PURPOSE_REGISTER})
        if record is None or not record.get('payload'):
            return APIResponse.error('No sign-up is pending for this email. Please register again.')

        try:
            meta = otp.issue(email, otp.PURPOSE_REGISTER,
                             payload=record['payload'], name=record['payload'].get('full_name', ''))
        except otp.OTPError as exc:
            return APIResponse.error(exc.message, status_code=exc.status_code)

        return APIResponse.success(data=meta, message='A new code is on its way.')


class RegisterVerifyView(APIView):
    """Step 2 of sign-up: check the code, create the account, sign the user in."""

    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        code  = str(request.data.get('code', '')).strip()

        if not email or not code:
            return APIResponse.error('Email and verification code are required.')

        try:
            record = otp.verify(email, code, otp.PURPOSE_REGISTER)
        except otp.OTPError as exc:
            return APIResponse.error(exc.message, status_code=exc.status_code)

        payload = record.get('payload') or {}
        if not payload.get('password_hash'):
            return APIResponse.error('This sign-up has expired. Please register again.')

        # Someone may have claimed the address while the code was in flight.
        if User.objects.filter(email__iexact=email).exists():
            otp.consume(email, otp.PURPOSE_REGISTER)
            return APIResponse.error('An account with this email already exists. Please log in.')

        user = create_user_from_pending(payload)
        otp.consume(email, otp.PURPOSE_REGISTER)

        _record_login(user, 'register')
        logger.info("New user registered (email verified): %s", user.email)
        return APIResponse.created(data=_session_payload(user), message='Registration successful.')


class PasswordResetRequestView(APIView):
    """
    Step 1 of a forgotten-password reset.

    The reply is the same whether or not the address is registered — otherwise
    this endpoint would happily confirm which emails have accounts.
    """

    permission_classes = [AllowAny]

    GENERIC = 'If an account exists for that email, a reset code is on its way.'

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        if not email:
            return APIResponse.error('Email is required.')

        user = User.objects.filter(email__iexact=email).first()
        meta = {
            'email': email,
            'expires_in_seconds': settings.OTP_TTL_MINUTES * 60,
            'resend_after_seconds': settings.OTP_RESEND_COOLDOWN_SECONDS,
        }

        if user is None:
            logger.info("Password reset requested for unknown email: %s", email)
            return APIResponse.success(data=meta, message=self.GENERIC)

        if not user.is_active:
            logger.info("Password reset requested for deactivated account: %s", email)
            return APIResponse.success(data=meta, message=self.GENERIC)

        try:
            meta = otp.issue(email, otp.PURPOSE_RESET, name=user.first_name)
        except otp.OTPError as exc:
            # Rate limits and mail failures are worth surfacing — they are about
            # the request, not about whether the account exists.
            return APIResponse.error(exc.message, status_code=exc.status_code)

        return APIResponse.success(data=meta, message=self.GENERIC)


class PasswordResetVerifyView(APIView):
    """Step 2: trade a correct code for a single-use reset ticket."""

    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        code  = str(request.data.get('code', '')).strip()

        if not email or not code:
            return APIResponse.error('Email and reset code are required.')

        try:
            otp.verify(email, code, otp.PURPOSE_RESET)
        except otp.OTPError as exc:
            return APIResponse.error(exc.message, status_code=exc.status_code)

        token = otp.issue_reset_ticket(email)
        return APIResponse.success(
            data={'reset_token': token,
                  'expires_in_seconds': settings.OTP_RESET_TOKEN_TTL_MINUTES * 60},
            message='Code verified. Choose a new password.',
        )


class PasswordResetConfirmView(APIView):
    """Step 3: set the new password against the ticket from step 2."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Could not reset your password.', serializer.errors)

        email = serializer.validated_data['email'].strip().lower()

        try:
            otp.check_reset_ticket(email, serializer.validated_data['reset_token'])
        except otp.OTPError as exc:
            return APIResponse.error(exc.message, status_code=exc.status_code)

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            otp.consume(email, otp.PURPOSE_RESET)
            return APIResponse.error('No account found with that email address.',
                                     status_code=status.HTTP_404_NOT_FOUND)

        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        otp.consume(email, otp.PURPOSE_RESET)

        logger.info("Password reset completed for %s", user.email)
        return APIResponse.success(message='Password updated. You can now log in.')


class LoginView(APIView):
    """Email + password sign-in for regular users."""

    permission_classes = [AllowAny]
    admin_only = False

    def post(self, request):
        email    = str(request.data.get('email', '')).strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return APIResponse.error('Email and password are required.')

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return APIResponse.error('No account found with that email address.',
                                     status_code=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return APIResponse.error('Incorrect password. Please try again.',
                                     status_code=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return APIResponse.error('This account has been deactivated. Contact an administrator.',
                                     status_code=status.HTTP_403_FORBIDDEN)

        if self.admin_only and not user.is_staff:
            return APIResponse.error('This account does not have administrator access.',
                                     status_code=status.HTTP_403_FORBIDDEN)

        _record_login(user, 'admin-password' if self.admin_only else 'password')
        logger.info("User logged in: %s", user.email)
        return APIResponse.success(data=_session_payload(user), message='Login successful.')


class AdminLoginView(LoginView):
    """Same credentials check as LoginView, but rejects non-staff accounts."""

    admin_only = True


class GoogleLoginView(APIView):
    """
    Sign in (or sign up) with a Google account.

    The frontend runs Google Identity Services and posts the resulting ID token
    as `credential`; it is verified against Google's public keys here, so the
    browser never gets to assert who it is.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        credential = request.data.get('credential', '')
        admin_only = bool(request.data.get('admin_only'))

        if not credential:
            return APIResponse.error('Missing Google credential.')

        client_id = settings.GOOGLE_CLIENT_ID
        if not client_id:
            return APIResponse.error(
                'Google sign-in is not configured on the server. Set GOOGLE_CLIENT_ID in backend/.env.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token as google_id_token
        except ImportError:
            return APIResponse.error(
                'Google sign-in requires the `google-auth` package (pip install -r requirements.txt).',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            info = google_id_token.verify_oauth2_token(
                credential, google_requests.Request(), client_id
            )
        except ValueError as exc:
            logger.warning("Rejected Google credential: %s", exc)
            return APIResponse.error('Could not verify that Google account.',
                                     status_code=status.HTTP_401_UNAUTHORIZED)

        if not info.get('email_verified'):
            return APIResponse.error('That Google account has no verified email address.',
                                     status_code=status.HTTP_401_UNAUTHORIZED)

        email = info.get('email', '')
        if not email:
            return APIResponse.error('That Google account did not share an email address.',
                                     status_code=status.HTTP_401_UNAUTHORIZED)

        # Admin sign-in must never silently create an account.
        if admin_only:
            user = User.objects.filter(email__iexact=email).first()
            if user is None or not user.is_staff:
                return APIResponse.error('This Google account does not have administrator access.',
                                         status_code=status.HTTP_403_FORBIDDEN)
            created = False
        else:
            user, created = get_or_create_google_user(email, info.get('name', ''))

        if not user.is_active:
            return APIResponse.error('This account has been deactivated. Contact an administrator.',
                                     status_code=status.HTTP_403_FORBIDDEN)

        _record_login(user, 'google')
        logger.info("Google sign-in: %s (new account: %s)", user.email, created)
        return APIResponse.success(
            data={**_session_payload(user), 'created': created},
            message='Account created.' if created else 'Login successful.',
        )


class GoogleConfigView(APIView):
    """Lets the frontend discover whether Google sign-in is usable."""

    permission_classes = [AllowAny]

    def get(self, request):
        return APIResponse.success(data={
            'client_id': settings.GOOGLE_CLIENT_ID,
            'enabled': bool(settings.GOOGLE_CLIENT_ID),
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return APIResponse.error('Refresh token is required.')
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("User logged out: %s", request.user.email)
            return APIResponse.success(message='Logged out successfully.')
        except TokenError as exc:
            return APIResponse.error(str(exc))


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return APIResponse.success(data=serializer.data)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return APIResponse.error('Update failed.', serializer.errors)
        serializer.save()
        return APIResponse.success(data=serializer.data, message='Profile updated.')


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return APIResponse.error('Current password is incorrect.')

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        logger.info("Password changed for user: %s", user.email)
        return APIResponse.success(message='Password changed successfully.')


class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return APIResponse.success(data=response.data, message='Token refreshed.')
        return APIResponse.error('Token refresh failed.', response.data,
                                 status_code=response.status_code)
