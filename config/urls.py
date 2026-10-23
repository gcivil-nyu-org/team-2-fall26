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
