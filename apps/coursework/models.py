from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone


class Priority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class Course(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses',
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    semester = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AssignmentQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(course__owner=user)

    def outstanding(self):
        return self.filter(status=Assignment.Status.INCOMPLETE).order_by(
            F('due_date').asc(nulls_last=True), 'title',
        )

    def completed(self):
        return self.filter(status=Assignment.Status.COMPLETE).order_by('-completed_at', 'title')

    def overdue(self):
        return self.filter(status=Assignment.Status.INCOMPLETE, due_date__lt=timezone.now())


class Assignment(models.Model):
    class Status(models.TextChoices):
        INCOMPLETE = 'incomplete', 'Incomplete'
        COMPLETE = 'complete', 'Complete'

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    title = models.CharField(max_length=200)
    # Nullable to preserve assignments created before deadlines were required.
    due_date = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, blank=True, default='')
    estimated_workload = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.5'))],
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INCOMPLETE)
    completed_at = models.DateTimeField(blank=True, null=True)

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        ordering = ['due_date', 'title']

    def __str__(self):
        return self.title

    @property
    def is_complete(self):
        return self.status == self.Status.COMPLETE

    @property
    def is_overdue(self):
        return (
            not self.is_complete
            and self.due_date is not None
            and self.due_date < timezone.now()
        )

    def mark_complete(self):
        self.status = self.Status.COMPLETE
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])

    def reopen(self):
        self.status = self.Status.INCOMPLETE
        self.completed_at = None
        self.save(update_fields=['status', 'completed_at'])


class ExamQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(course__owner=user)

    def upcoming(self):
        return self.filter(starts_at__gte=timezone.now()).order_by('starts_at', 'title')


class Exam(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='exams',
    )
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, blank=True, default='')
    estimated_workload = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.5'))],
    )

    objects = ExamQuerySet.as_manager()

    class Meta:
        ordering = ['starts_at', 'title']

    def __str__(self):
        return self.title
