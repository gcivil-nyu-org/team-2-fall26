from datetime import datetime, timezone as dt_timezone
from io import StringIO
from html import escape
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .engage import CAREER_CATEGORY, FeedError, MAX_FEED_BYTES, NoRedirects, parse_feed, sync_feed
from .models import Event, EventFeedState

NOW = datetime(2026, 11, 16, 12, tzinfo=dt_timezone.utc)


def item(source_id='123', title='Career workshop', start='Mon, 16 Nov 2026 23:00:00 GMT',
         end='Tue, 17 Nov 2026 01:00:00 GMT', status='confirmed', category=CAREER_CATEGORY,
         description='<p>Meet employers.</p><script>alert(1)</script>', url=None):
    return f'''<item><title>{title}</title><link>{url or f'https://engage.nyu.edu/event/{source_id}'}</link>
    <description><![CDATA[{description}]]></description><category>{escape(category)}</category>
    <start xmlns="events">{start}</start><end xmlns="events">{end}</end>
    <location xmlns="events">Brooklyn</location><host xmlns="events">Career Hub</host>
    <status xmlns="events">{status}</status></item>'''


def feed(*items):
    return ('<rss version="2.0"><channel>' + ''.join(items or [item()]) + '</channel></rss>').encode()


class ImportTests(TestCase):
    def test_repeat_sync_updates_in_place_and_replaces_categories(self):
        sync_feed(feed())
        event = Event.objects.get()
        self.assertEqual(event.description, 'Meet employers.')
        self.assertEqual(event.starts_at.hour, 23)
        sync_feed(feed(item(title='New title', status='cancelled', category='Arts')))
        event.refresh_from_db()
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(event.title, 'New title')
        self.assertEqual(event.status, 'cancelled')
        self.assertEqual(list(event.categories.values_list('name', flat=True)), ['Arts'])

    def test_bad_feed_preserves_data_and_refresh_time(self):
        sync_feed(feed())
        original = EventFeedState.objects.get().last_success_at
        for bad in (b'<html>Oops</html>', b'<rss>', b'<rss><channel/></rss>',
                    b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel>&x;</channel></rss>'):
            with self.subTest(bad=bad), self.assertRaises(FeedError):
                sync_feed(bad)
            self.assertEqual(EventFeedState.objects.get().last_success_at, original)
            self.assertEqual(Event.objects.count(), 1)

    def test_invalid_items_are_reported_and_missing_items_are_retained(self):
        sync_feed(feed(item(), item('456')))
        imported, skipped = sync_feed(feed(item(), item('789', start='bad'),
                                          item('333', url='javascript:alert(1)')))
        self.assertEqual((imported, skipped), (1, 2))
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(EventFeedState.objects.get().skipped_count, 2)

    def test_conflicting_duplicates_abort_whole_import(self):
        with self.assertRaises(FeedError):
            sync_feed(feed(item(), item(title='Different')))
        self.assertFalse(Event.objects.exists())

    def test_title_with_bare_ampersand_is_preserved(self):
        records, skipped = parse_feed(feed(item(title='Animation Q&amp;A!')))
        self.assertEqual(records['123']['title'], 'Animation Q&A!')
        self.assertEqual(skipped, 0)

    def test_feed_size_and_redirect_limits(self):
        with self.assertRaises(FeedError):
            parse_feed(b' ' * (MAX_FEED_BYTES + 1))
        with self.assertRaises(FeedError):
            NoRedirects().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/')

    def test_download_failure_returns_command_error_and_preserves_data(self):
        sync_feed(feed())
        with patch('apps.events.engage.download_feed', side_effect=URLError('offline')):
            with self.assertRaises(CommandError):
                call_command('sync_engage_events', stdout=StringIO())
        self.assertEqual(Event.objects.count(), 1)

    def test_database_failure_rolls_back_entire_batch(self):
        sync_feed(feed())
        original = EventFeedState.objects.get().last_success_at
        with patch('apps.events.models.EventCategory.objects.get_or_create', side_effect=RuntimeError('db problem')):
            with self.assertRaises(RuntimeError):
                sync_feed(feed(item(title='Changed')))
        self.assertEqual(Event.objects.get().title, 'Career workshop')
        self.assertEqual(EventFeedState.objects.get().last_success_at, original)


@patch('apps.events.views.timezone.now', return_value=NOW)
class EventAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='events', email='events@nyu.edu', password='test-password')
        self.client.force_login(self.user)
        with patch('apps.events.engage.timezone.now', return_value=NOW):
            sync_feed(feed(item(), item('456', title='Art tour', category='Arts'),
                       item('789', status='cancelled'),
                       item('888', start='Sun, 15 Nov 2026 12:00:00 GMT', end='Sun, 15 Nov 2026 13:00:00 GMT')))

    def test_authentication_required_and_read_only(self, now):
        self.client.logout()
        self.assertEqual(self.client.get('/api/events/').status_code, 401)
        self.assertEqual(self.client.get('/api/events/1/').status_code, 401)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/api/events/').status_code, 405)

    def test_discovery_excludes_cancelled_and_past_events(self, now):
        data = self.client.get('/api/events/').json()
        self.assertEqual(data['count'], 2)
        self.assertTrue(data['last_synced_at'])
        self.assertEqual(set(data['categories']), {'Arts', CAREER_CATEGORY})
        self.assertNotIn('description', data['events'][0])

    def test_old_and_already_started_events_do_not_appear_even_if_they_end_later(self, now):
        sync_feed(feed(
            item('111', title='October series', start='Thu, 01 Oct 2026 12:00:00 GMT',
                 end='Tue, 01 Dec 2026 12:00:00 GMT', category='Old series'),
            item('222', title='Started earlier today', start='Mon, 16 Nov 2026 11:00:00 GMT',
                 end='Mon, 16 Nov 2026 17:00:00 GMT', category='In progress'),
            item('333', title='Starting now', start='Mon, 16 Nov 2026 12:00:00 GMT',
                 end='Mon, 16 Nov 2026 17:00:00 GMT'),
        ))
        data = self.client.get('/api/events/').json()
        self.assertEqual(data['count'], 2)
        self.assertNotIn('Old series', data['categories'])
        self.assertNotIn('In progress', data['categories'])
        # Selecting historical dates cannot reintroduce events we can no longer attend.
        old = self.client.get('/api/events/', {'date_from': '2026-10-01', 'date_to': '2026-10-31'}).json()
        self.assertEqual(old['events'], [])

    def test_discovery_removes_event_once_its_start_passes(self, now):
        self.assertEqual(self.client.get('/api/events/').json()['count'], 2)
        now.return_value = datetime(2026, 11, 16, 23, 1, tzinfo=dt_timezone.utc)
        self.assertEqual(self.client.get('/api/events/').json()['count'], 0)

    def test_career_category_and_text_search(self, now):
        for params in ({'career': 'true'}, {'category': CAREER_CATEGORY}, {'q': 'workshop'}):
            data = self.client.get('/api/events/', params).json()
            self.assertEqual(data['count'], 1)
            self.assertEqual(data['events'][0]['title'], 'Career workshop')
        self.assertEqual(self.client.get('/api/events/', {'q': 'Career Hub'}).json()['count'], 2)
        self.assertEqual(self.client.get('/api/events/', {'career': 'true', 'category': 'Arts'}).json()['count'], 0)

    def test_date_filter_uses_eastern_day_not_utc_day(self, now):
        # End is Nov 17 UTC, but both start/end occur on Nov 16 Eastern.
        self.assertEqual(self.client.get('/api/events/', {'date_from': '2026-11-17'}).json()['count'], 0)
        self.assertEqual(self.client.get('/api/events/', {'date_to': '2026-11-16'}).json()['count'], 2)

    def test_dst_date_boundaries(self, now):
        EventFeedState.objects.update(last_success_at=None)
        with patch('apps.events.views.timezone.now', return_value=datetime(2026, 10, 31, tzinfo=dt_timezone.utc)):
            sync_feed(feed(item('999', start='Mon, 02 Nov 2026 04:00:00 GMT', end='Mon, 02 Nov 2026 04:30:00 GMT')))
            # 23:00 EST on Nov 1, the 25-hour day when clocks move back.
            data = self.client.get('/api/events/', {'date_from': '2026-11-01', 'date_to': '2026-11-01'}).json()
            self.assertEqual([event['title'] for event in data['events']], ['Career workshop'])

    def test_bad_filters_are_400(self, now):
        for params in ({'date_from': '2026-02-30'}, {'date_to': 'nonsense'}, {'page': 'bad'}, {'page': '0'},
                       {'date_from': '2026-11-20', 'date_to': '2026-11-19'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get('/api/events/', params).status_code, 400)

    def test_detail_retains_cancelled_notice_and_safe_description(self, now):
        event = Event.objects.get(source_id='789')
        data = self.client.get(f'/api/events/{event.pk}/').json()['event']
        self.assertEqual(data['status'], 'cancelled')
        self.assertEqual(data['description'], 'Meet employers.')
        self.assertEqual(self.client.get('/api/events/99999/').status_code, 404)

    def test_pagination_is_stable_without_duplicates(self, now):
        sync_feed(feed(*(item(str(n)) for n in range(1000, 1030))))
        one = self.client.get('/api/events/').json()
        two = self.client.get('/api/events/', {'page': 2}).json()
        self.assertEqual(one['count'], 32)
        self.assertEqual(len(one['events']), 24)
        self.assertEqual(len(two['events']), 8)
        self.assertFalse({x['id'] for x in one['events']} & {x['id'] for x in two['events']})

    def test_missing_or_old_sync_is_reported(self, now):
        EventFeedState.objects.update(last_success_at=NOW.replace(day=14))
        self.assertTrue(self.client.get('/api/events/').json()['stale'])
        Event.objects.all().delete()
        EventFeedState.objects.all().delete()
        data = self.client.get('/api/events/').json()
        self.assertTrue(data['stale'])
        self.assertIsNone(data['last_synced_at'])
        self.assertEqual(data['events'], [])
