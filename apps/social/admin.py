from django.contrib import admin

from .models import DirectMessage, FriendRequest


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'status', 'created_at']
    list_filter = ['status']
    list_select_related = ['sender', 'recipient']


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'recipient', 'created_at']
    list_filter = ['created_at']
    list_select_related = ['sender', 'recipient']
    readonly_fields = ['sender', 'recipient', 'body', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
