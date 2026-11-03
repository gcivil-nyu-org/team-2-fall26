from django.urls import path

from . import views

app_name = 'social'

urlpatterns = [
    path('friends/', views.friends_view, name='friends'),
    path('friends/requests/', views.friend_requests_view, name='friend_requests'),
    path('friends/requests/<int:pk>/', views.friend_request_view, name='friend_request'),
    path('friends/<int:pk>/', views.friend_profile_view, name='friend_profile'),
    path('posts/', views.food_posts_view, name='posts'),
]
