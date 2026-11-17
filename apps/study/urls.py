from django.urls import path

from . import views

app_name = 'study'

urlpatterns = [
    path('albert-import/', views.albert_import_view, name='albert_import'),
    path('availability/', views.availability_view, name='availability'),
    path('sessions/<int:session_id>/', views.session_view, name='session'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('generate/', views.generate_view, name='generate'),
]
