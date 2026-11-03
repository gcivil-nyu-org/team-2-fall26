from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F('start_time')), name='availability_positive_duration'),
        ]

    def __str__(self):
        return f'{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M} UTC'


class StudySession(models.Model):
    # Ownership and course/task details come from the assignment, avoiding
    # independent owner/course fields that could disagree with one another.
    assignment = models.ForeignKey('coursework.Assignment', on_delete=models.CASCADE, related_name='study_sessions')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ['starts_at', 'pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='study_session_positive_duration'),
        ]

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'The session must end after it starts.'})

    def __str__(self):
        return f'{self.assignment.title} — {self.starts_at}'
