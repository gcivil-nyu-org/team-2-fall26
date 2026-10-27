from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.api.urls')),
    path('app/', TemplateView.as_view(template_name='react_app.html'), name='react_app'),
    path('app/<path:path>', TemplateView.as_view(template_name='react_app.html')),
    path('', RedirectView.as_view(url='/app/dashboard', permanent=False)),
]

if settings.DEBUG:
    # In production, uploaded media should be served from persistent storage
    # (e.g. S3 via django-storages) rather than the app server's local disk,
    # which is not durable on Elastic Beanstalk. See README.md.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
