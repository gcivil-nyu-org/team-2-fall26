from django.urls import path

from . import views

app_name = 'study'

urlpatterns = [
    path('availability/', views.availability_view, name='availability'),
    path('sessions/<int:session_id>/', views.session_view, name='session'),
    path('calendar/', views.calendar_view, name='calendar'),
]
