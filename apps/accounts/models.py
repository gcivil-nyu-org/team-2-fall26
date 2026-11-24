from django.contrib.auth.models import AbstractUser
from django.db import models


# How early a study-session reminder appears on the dashboard (#37).
STUDY_REMINDER_MINUTE_CHOICES = (15, 30, 60, 120)
# How far ahead an assignment or exam shows up as "due soon" on the dashboard.
DEADLINE_REMINDER_HOUR_CHOICES = (6, 24, 48, 72)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    profile_picture = models.ImageField(upload_to='profile-pictures/', blank=True, null=True)
    bio = models.TextField(max_length=300, blank=True)
    # Privacy (#31): what other students may see. Everything is visible by
    # default (the behavior before this existed); a student opts out per
    # field. The name is intentionally not hideable - friends and friend
    # requests need something to identify who they are looking at.
    show_email = models.BooleanField(default=True)
    show_bio = models.BooleanField(default=True)
    show_profile_picture = models.BooleanField(default=True)
    # Notification preferences (#37). Defaults match how reminders behaved
    # before this existed: on, one hour ahead.
    study_reminders_enabled = models.BooleanField(default=True)
    study_reminder_minutes = models.PositiveSmallIntegerField(
        default=60, choices=[(minutes, f'{minutes} minutes') for minutes in STUDY_REMINDER_MINUTE_CHOICES],
    )
    deadline_reminders_enabled = models.BooleanField(default=True)
    deadline_reminder_hours = models.PositiveSmallIntegerField(
        default=24, choices=[(hours, f'{hours} hours') for hours in DEADLINE_REMINDER_HOUR_CHOICES],
    )
    # Badges in the sidebar for pending friend requests and unread messages.
    friend_request_alerts_enabled = models.BooleanField(default=True)
    message_alerts_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.email
