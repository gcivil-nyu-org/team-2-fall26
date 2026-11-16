from urllib.error import URLError

from django.core.management.base import BaseCommand, CommandError

from apps.events.engage import FeedError, sync_feed


class Command(BaseCommand):
    help = 'Import/update events from the fixed public NYU Engage RSS feed.'

    def handle(self, *args, **options):
        try:
            imported, skipped = sync_feed()
        except (FeedError, URLError, OSError, TimeoutError) as exc:
            raise CommandError(f'Engage sync failed; previous data retained: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Imported {imported} events; skipped {skipped} invalid items.'))
