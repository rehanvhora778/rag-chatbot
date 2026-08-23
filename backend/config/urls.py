from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import health_check

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/health/', health_check, name='health_check'),
    path('api/auth/',        include('apps.authentication.urls')),
    path('api/documents/',   include('apps.documents.urls')),
    path('api/chat/',        include('apps.chat.urls')),
    path('api/analytics/',   include('apps.analytics.urls')),
    path('api/admin-panel/', include('apps.admin_panel.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
