from django.urls import path
from django.contrib.auth.views import LoginView
from . import views
from .forms import EmailAuthenticationForm

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', LoginView.as_view(
        template_name='accounts/login.html',
        authentication_form=EmailAuthenticationForm,
        redirect_authenticated_user=True,
    ), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
]
