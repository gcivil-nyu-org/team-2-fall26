from django.contrib import admin

from .models import FoodPost, FriendRequest


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'status', 'created_at']
    list_filter = ['status']
    list_select_related = ['sender', 'recipient']


@admin.register(FoodPost)
class FoodPostAdmin(admin.ModelAdmin):
    list_display = ['place_name', 'author', 'rating', 'created_at']
    list_select_related = ['author']
    search_fields = ['place_name', 'cuisine', 'location']
