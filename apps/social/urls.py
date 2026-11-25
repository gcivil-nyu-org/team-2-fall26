from django.urls import path

from . import views

app_name = 'social'

urlpatterns = [
    path('alerts/', views.alerts_view, name='alerts'),
    path('friends/', views.friends_view, name='friends'),
    path('messages/<int:pk>/', views.conversation_view, name='conversation'),
    path('friends/seen/', views.friends_seen_view, name='friends_seen'),
    path('friends/requests/', views.friend_requests_view, name='friend_requests'),
    path('friends/requests/<int:pk>/', views.friend_request_view, name='friend_request'),
    path('friends/<int:pk>/', views.friend_profile_view, name='friend_profile'),
    path('posts/', views.food_posts_view, name='posts'),
    path('posts/<int:pk>/', views.food_post_view, name='post'),
    path('posts/<int:pk>/save/', views.food_post_save_view, name='post_save'),
    path('posts/<int:pk>/comments/', views.food_post_comments_view, name='post_comments'),
    path('posts/<int:pk>/report/', views.food_post_report_view, name='post_report'),
    path('comments/<int:pk>/report/', views.comment_report_view, name='comment_report'),
    path('posts/<int:pk>/share/', views.food_post_share_view, name='post_share'),
    path('posts/saved/', views.saved_food_posts_view, name='saved_posts'),
]
