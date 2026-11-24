from django.db import models


class EventCategory(models.Model):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Event(models.Model):
    # This first importer has one source; Engage's numeric ID is stable across edits.
    source_id = models.CharField(max_length=40, unique=True)
    source_url = models.URLField(max_length=300)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=1000, blank=True)
    host = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20)
    categories = models.ManyToManyField(EventCategory, blank=True)
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ['starts_at', 'pk']


class EventFeedState(models.Model):
    # One row, also serializes competing import writes.
    source = models.CharField(max_length=40, primary_key=True, default='engage')
    last_success_at = models.DateTimeField(null=True)
    imported_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)


class SavedEvent(models.Model):
    owner = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='saved_events')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='saves')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'event'], name='saved_event_once_per_owner')]
