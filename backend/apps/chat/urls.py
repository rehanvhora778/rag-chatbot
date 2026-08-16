from django.urls import path
from .views import (
    ChatSessionListView, ChatSessionDetailView,
    SendMessageView, ChatSearchView, ExportChatPDFView, ChatConfigView,
)

urlpatterns = [
    path('sessions/',                           ChatSessionListView.as_view(),   name='chat_sessions'),
    path('sessions/<str:session_id>/',          ChatSessionDetailView.as_view(), name='chat_session_detail'),
    path('sessions/<str:session_id>/message/',  SendMessageView.as_view(),       name='chat_send_message'),
    path('sessions/<str:session_id>/export/',   ExportChatPDFView.as_view(),     name='chat_export_pdf'),
    path('search/',                             ChatSearchView.as_view(),        name='chat_search'),
    path('config/',                             ChatConfigView.as_view(),        name='chat_config'),
]
