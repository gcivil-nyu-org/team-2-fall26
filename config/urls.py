from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('', RedirectView.as_view(pattern_name='accounts:dashboard', permanent=False)),

    # path('', include('apps.coursework.urls')),  # replace the line above once apps/coursework exists
]
