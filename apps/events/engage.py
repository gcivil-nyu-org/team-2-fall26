"""Public Engage RSS import. Network and parsing finish before any data is changed."""
import re
from datetime import timezone as dt_timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from django.db import transaction
from django.utils import timezone

from .models import Event, EventCategory, EventFeedState

FEED_URL = 'https://engage.nyu.edu/events.rss'
MAX_FEED_BYTES = 5 * 1024 * 1024
CAREER_CATEGORY = 'Professional & Career Development'


class FeedError(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never follow a source redirect to an arbitrary host or internal address.
        raise FeedError('Engage redirected the feed; check its public URL before retrying.')


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ('p', 'div', 'li') and not self.hidden:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value)
    parser.close()
    return '\n'.join(line for part in ''.join(parser.parts).splitlines()
                     if (line := ' '.join(part.split())))


def download_feed():
    request = Request(FEED_URL, headers={
        'User-Agent': 'SemesterPilot/1.0 (NYU public event discovery)',
        'Accept': 'application/rss+xml, application/xml',
    })
    with build_opener(NoRedirects()).open(request, timeout=20) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise FeedError('Engage feed exceeds the 5 MB limit.')
    return data


def parse_feed(data):
    if len(data) > MAX_FEED_BYTES:
        raise FeedError('Engage feed exceeds the 5 MB limit.')
    try:
        root = fromstring(data, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as exc:
        raise FeedError('Engage returned invalid or unsafe XML.') from exc
    if root.tag != 'rss' or root.find('channel') is None:
        raise FeedError('Expected an Engage RSS channel.')
    records = {}
    skipped = 0
    for item in root.findall('./channel/item'):
        def text(name):
            return (item.findtext(name) or '').strip()
        try:
            url = text('link')
            match = re.fullmatch(r'https://engage\.nyu\.edu/event/(\d{1,40})/?', url)
            title = plain_text(text('title'))
            starts = parsedate_to_datetime(text('{events}start'))
            ends = parsedate_to_datetime(text('{events}end'))
            status = text('{events}status').lower()
            if (not match or not title or len(title) > 500 or starts.tzinfo is None
                    or ends.tzinfo is None or ends < starts
                    or status not in ('confirmed', 'cancelled')):
                raise ValueError('Invalid event fields')
            record = {
                'source_url': f'https://engage.nyu.edu/event/{match[1]}',
                'title': title,
                'description': plain_text(text('description')),
                'starts_at': starts.astimezone(dt_timezone.utc),
                'ends_at': ends.astimezone(dt_timezone.utc),
                'location': plain_text(text('{events}location'))[:1000],
                'host': plain_text(text('{events}host'))[:500],
                'status': status,
                'category_names': sorted({plain_text(c.text or '')[:200] for c in item.findall('category')
                                          if plain_text(c.text or '').strip()}),
            }
            if match[1] in records and records[match[1]] != record:
                raise FeedError('Feed contains conflicting duplicate event IDs.')
            records[match[1]] = record
        except (TypeError, ValueError, OverflowError) as exc:
            if isinstance(exc, FeedError):
                raise
            skipped += 1
    if not records:
        raise FeedError('Feed has no valid events; previous data was preserved.')
    return records, skipped


def sync_feed(data=None):
    started = timezone.now()
    records, skipped = parse_feed(download_feed() if data is None else data)
    with transaction.atomic():
        state, _ = EventFeedState.objects.get_or_create(source='engage')
        state = EventFeedState.objects.select_for_update().get(pk=state.pk)
        if state.last_success_at and state.last_success_at > started:
            raise FeedError('A newer import already completed; retry the sync.')
        for source_id, values in records.items():
            values = values.copy()
            names = values.pop('category_names')
            event, _ = Event.objects.update_or_create(
                source_id=source_id, defaults={**values, 'last_seen_at': started},
            )
            event.categories.set([EventCategory.objects.get_or_create(name=name)[0] for name in names])
        state.last_success_at = started
        state.imported_count = len(records)
        state.skipped_count = skipped
        state.save()
    # Absence from this rolling public feed does not imply cancellation.
    return len(records), skipped
