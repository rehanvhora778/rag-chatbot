from django.urls import path

from .views import (
    ChatConfigView,
    ChatSearchView,
    ChatSessionDetailView,
    ChatSessionListView,
    ChatStreamView,
    ExportChatPDFView,
    MessageFeedbackView,
    SendMessageView,
)

urlpatterns = [
    path('sessions/',                           ChatSessionListView.as_view(),   name='chat_sessions'),
    path('sessions/<str:session_id>/',          ChatSessionDetailView.as_view(), name='chat_session_detail'),
    path('sessions/<str:session_id>/message/',  SendMessageView.as_view(),       name='chat_send_message'),
    # Same input as /message/, streamed. Kept as a separate route rather than a
    # flag on the existing one because the response type differs entirely:
    # text/event-stream against application/json, and a client has to choose
    # deliberately which it can handle.
    path('sessions/<str:session_id>/stream/',   ChatStreamView.as_view(),        name='chat_stream_message'),
    path('sessions/<str:session_id>/export/',   ExportChatPDFView.as_view(),     name='chat_export_pdf'),
    path('messages/<str:message_id>/feedback/', MessageFeedbackView.as_view(),   name='chat_message_feedback'),
    path('search/',                             ChatSearchView.as_view(),        name='chat_search'),
    path('config/',                             ChatConfigView.as_view(),        name='chat_config'),
]
