from django.urls import path

from .views import UserAnalyticsView, UserDashboardView

urlpatterns = [
    path('',          UserAnalyticsView.as_view(), name='user_analytics'),
    path('dashboard/', UserDashboardView.as_view(), name='user_dashboard'),
]
