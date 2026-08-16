from django.urls import path
from .views import (
    RegisterView, RegisterVerifyView, RegisterResendView,
    LoginView, AdminLoginView, GoogleLoginView, GoogleConfigView,
    PasswordResetRequestView, PasswordResetVerifyView, PasswordResetConfirmView,
    LogoutView, ProfileView, ChangePasswordView, CustomTokenRefreshView,
)

urlpatterns = [
    path('register/',         RegisterView.as_view(),           name='auth_register'),
    path('register/verify/',  RegisterVerifyView.as_view(),     name='auth_register_verify'),
    path('register/resend/',  RegisterResendView.as_view(),     name='auth_register_resend'),
    path('password-reset/',        PasswordResetRequestView.as_view(), name='auth_password_reset'),
    path('password-reset/verify/', PasswordResetVerifyView.as_view(),  name='auth_password_reset_verify'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth_password_reset_confirm'),
    path('login/',            LoginView.as_view(),              name='auth_login'),
    path('admin/login/',      AdminLoginView.as_view(),         name='auth_admin_login'),
    path('google/',           GoogleLoginView.as_view(),        name='auth_google'),
    path('google/config/',    GoogleConfigView.as_view(),       name='auth_google_config'),
    path('logout/',           LogoutView.as_view(),             name='auth_logout'),
    path('token/refresh/',    CustomTokenRefreshView.as_view(), name='auth_token_refresh'),
    path('profile/',          ProfileView.as_view(),            name='auth_profile'),
    path('change-password/',  ChangePasswordView.as_view(),     name='auth_change_password'),
]
