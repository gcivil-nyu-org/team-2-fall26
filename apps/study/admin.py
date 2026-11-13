from django.contrib import admin

from .models import AvailabilityBlock, StudySession


@admin.register(AvailabilityBlock)
class AvailabilityBlockAdmin(admin.ModelAdmin):
    list_display = ['owner', 'weekday', 'start_time', 'end_time']
    list_filter = ['weekday']


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'exam', 'starts_at', 'ends_at', 'is_locked', 'is_complete']
    list_select_related = ['assignment', 'exam']
