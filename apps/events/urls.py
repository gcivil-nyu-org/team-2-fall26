from django.urls import path
from . import views

app_name = 'events'
urlpatterns = [
    path('', views.events_view, name='list'),
    path('<int:pk>/', views.event_view, name='detail'),
]
