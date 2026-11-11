from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return self.email
