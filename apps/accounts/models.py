from django.contrib.auth.models import AbstractUser
from django.db import models


# How early a study-session reminder appears on the dashboard (#37).
STUDY_REMINDER_MINUTE_CHOICES = (15, 30, 60, 120)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    profile_picture = models.ImageField(upload_to='profile-pictures/', blank=True, null=True)
    bio = models.TextField(max_length=300, blank=True)
    # Notification preferences (#37). Defaults match how reminders behaved
    # before this existed: on, one hour ahead.
    study_reminders_enabled = models.BooleanField(default=True)
    study_reminder_minutes = models.PositiveSmallIntegerField(
        default=60, choices=[(minutes, f'{minutes} minutes') for minutes in STUDY_REMINDER_MINUTE_CHOICES],
    )

    def __str__(self):
        return self.email
