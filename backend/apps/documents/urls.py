from django.urls import path

from .views import DocumentDetailView, DocumentListUploadView, DocumentSummaryView

urlpatterns = [
    path('',                                DocumentListUploadView.as_view(), name='document_list_upload'),
    path('<str:document_id>/',              DocumentDetailView.as_view(),     name='document_detail'),
    path('<str:document_id>/summary/',      DocumentSummaryView.as_view(),    name='document_summary'),
]
