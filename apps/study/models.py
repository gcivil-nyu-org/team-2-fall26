from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ClassMeeting(models.Model):
    course = models.ForeignKey('coursework.Course', on_delete=models.CASCADE, related_name='class_meetings')
    term = models.CharField(max_length=64)
    source_uid = models.CharField(max_length=255)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)


class AvailabilityBlock(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='availability_blocks')
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ['weekday', 'start_time']
        constraints = [
            models.CheckConstraint(condition=models.Q(weekday__gte=0, weekday__lte=6), name='availability_valid_weekday'),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')) | models.Q(end_time=time.min, start_time__gt=time.min),
                name='availability_positive_duration',
            ),
        ]

    def __str__(self):
        return f'{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M} Eastern'


class StudySessionQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(models.Q(assignment__course__owner=user) | models.Q(exam__course__owner=user))

    def with_course(self):
        return self.select_related('assignment__course', 'exam__course')


class StudySession(models.Model):
    # Each session studies for exactly one assignment or exam. Ownership and
    # course details come from that item, avoiding independent owner/course
    # fields that could disagree with one another.
    assignment = models.ForeignKey('coursework.Assignment', on_delete=models.CASCADE, related_name='study_sessions', null=True, blank=True)
    exam = models.ForeignKey('coursework.Exam', on_delete=models.CASCADE, related_name='study_sessions', null=True, blank=True)
    is_locked = models.BooleanField(default=False)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    objects = StudySessionQuerySet.as_manager()

    class Meta:
        ordering = ['starts_at', 'pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='study_session_positive_duration'),
            models.CheckConstraint(
                condition=models.Q(assignment__isnull=False, exam__isnull=True) | models.Q(assignment__isnull=True, exam__isnull=False),
                name='study_session_one_item',
            ),
        ]

    @property
    def item(self):
        return self.assignment or self.exam

    @property
    def course(self):
        return self.item.course

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'The session must end after it starts.'})
        if (self.assignment_id is None) == (self.exam_id is None):
            raise ValidationError('A study session belongs to exactly one assignment or exam.')

    def __str__(self):
        return f'{self.item.title} — {self.starts_at}'
