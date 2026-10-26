from django.urls import path

from . import views


app_name = 'api'

urlpatterns = [
    path('session/', views.session_view, name='session'),
    path('auth/login/', views.login_view, name='login'),
    path('auth/signup/', views.signup_view, name='signup'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/password-reset/', views.password_reset_request_view, name='password_reset_request'),
    path('auth/password-reset/confirm/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('courses/', views.courses_view, name='courses'),
    path('courses/<int:pk>/', views.course_view, name='course'),
    path('courses/<int:pk>/assignments/', views.course_assignments_view, name='course_assignments'),
    path('assignments/', views.assignments_view, name='assignments'),
    path('assignments/<int:pk>/', views.assignment_view, name='assignment'),
]
