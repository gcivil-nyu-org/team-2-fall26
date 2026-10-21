from django.urls import path
from . import views

app_name = 'coursework'

urlpatterns = [
    path('courses/add/', views.course_create_view, name='course_add'),
    path('courses/<int:pk>/', views.course_detail_view, name='course_detail'),
    path('courses/<int:pk>/assignments/add/', views.assignment_create_view, name='assignment_add'),
    path('assignments/completed/', views.completed_assignments_view, name='completed_assignments'),
    path('assignments/<int:pk>/complete/', views.assignment_complete_view, name='assignment_complete'),
    path('assignments/<int:pk>/reopen/', views.assignment_reopen_view, name='assignment_reopen'),
]
