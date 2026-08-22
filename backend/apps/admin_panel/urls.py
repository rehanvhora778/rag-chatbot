from django.urls import path

from .views import (
    AdminChatSessionListView,
    AdminDocumentDetailView,
    AdminDocumentListView,
    AdminMetricsView,
    AdminSystemStatsView,
    AdminUserDetailView,
    AdminUserListView,
)

urlpatterns = [
    path('metrics/',                        AdminMetricsView.as_view(),        name='admin_metrics'),
    path('stats/',                          AdminSystemStatsView.as_view(),    name='admin_stats'),
    path('users/',                          AdminUserListView.as_view(),       name='admin_users'),
    path('users/<int:user_id>/',            AdminUserDetailView.as_view(),     name='admin_user_detail'),
    path('documents/',                      AdminDocumentListView.as_view(),   name='admin_documents'),
    path('documents/<str:doc_id>/',         AdminDocumentDetailView.as_view(), name='admin_document_detail'),
    path('chats/',                          AdminChatSessionListView.as_view(), name='admin_chats'),
    path('chats/<str:session_id>/',         AdminChatSessionListView.as_view(), name='admin_chat_detail'),
]
