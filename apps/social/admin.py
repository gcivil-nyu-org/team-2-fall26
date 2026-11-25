from django.contrib import admin
from django.utils.html import format_html
from django.utils.text import Truncator

from .models import ContentReport, DirectMessage, FoodPost, FriendRequest, PostComment, SavedPost


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['sender', 'recipient', 'status', 'created_at']
    list_filter = ['status']
    list_select_related = ['sender', 'recipient']


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'recipient', 'shares_post', 'created_at']
    list_filter = ['created_at', 'shares_post']
    list_select_related = ['sender', 'recipient']
    readonly_fields = ['sender', 'recipient', 'body', 'shared_post', 'shares_post', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FoodPost)
class FoodPostAdmin(admin.ModelAdmin):
    list_display = ['place_name', 'author', 'rating', 'created_at']
    list_select_related = ['author']
    search_fields = ['place_name', 'cuisine', 'location']


@admin.register(SavedPost)
class SavedPostAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']
    list_select_related = ['user', 'post']


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ['post', 'author', 'created_at']
    list_select_related = ['post', 'author']
    search_fields = ['body']


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    # #67: the reported-content queue, newest first. Reports are read-only
    # here; marking them reviewed is #56 and removing content is #57.
    list_display = ['created_at', 'content_type_label', 'reported_content', 'content_author', 'reason', 'reporter', 'view_on_site_link']
    list_filter = ['reason', 'created_at']
    list_select_related = ['reporter', 'post__author', 'comment__author', 'comment__post']
    search_fields = ['reporter__email', 'details', 'post__place_name', 'comment__body']
    readonly_fields = [
        'created_at', 'content_type_label', 'reported_content', 'content_author', 'reason', 'details', 'reporter',
        'view_on_site_link',
    ]
    fields = readonly_fields

    @admin.display(description='Type')
    def content_type_label(self, report):
        return report.content_type_label

    @admin.display(description='Reported content')
    def reported_content(self, report):
        if report.post_id:
            return report.post.place_name
        return f'“{Truncator(report.comment.body).chars(80)}” on {report.comment.post.place_name}'

    @admin.display(description='Posted by')
    def content_author(self, report):
        return report.content.author

    @admin.display(description='Open')
    def view_on_site_link(self, report):
        post_id = report.post_id or report.comment.post_id
        return format_html('<a href="/app/community/posts/{}" target="_blank" rel="noopener">View on site</a>', post_id)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
