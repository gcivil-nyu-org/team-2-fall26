from django.contrib import admin
from .models import Assignment, Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'semester', 'owner')
    list_filter = ('semester',)
    search_fields = ('name', 'code')


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'due_date', 'status')
    list_filter = ('status',)
