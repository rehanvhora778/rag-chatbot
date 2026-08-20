from django.urls import path

from .views import (
    DocumentDetailView,
    DocumentListUploadView,
    DocumentReprocessView,
    DocumentStatusView,
    DocumentSummaryView,
)

urlpatterns = [
    path('',                              DocumentListUploadView.as_view(), name='document_list_upload'),
    # Before the <str:document_id> route, or "status" is captured as an id.
    path('status/',                       DocumentStatusView.as_view(),     name='document_status'),
    path('<str:document_id>/',            DocumentDetailView.as_view(),     name='document_detail'),
    path('<str:document_id>/summary/',    DocumentSummaryView.as_view(),    name='document_summary'),
    path('<str:document_id>/reprocess/',  DocumentReprocessView.as_view(),  name='document_reprocess'),
]
