from django.contrib import admin
from .models import Assignment, Course, Exam


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'semester', 'owner')
    list_filter = ('semester',)
    search_fields = ('name', 'code')


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'due_date', 'priority', 'estimated_workload', 'status')
    list_filter = ('status', 'priority')


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'starts_at', 'priority', 'estimated_workload', 'location')
    list_filter = ('priority',)
