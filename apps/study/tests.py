import json
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.coursework.models import Assignment, Course
from .models import AvailabilityBlock, StudySession


def instant(value):
    return datetime.fromisoformat(value).replace(tzinfo=dt_timezone.utc)


class StudyTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='study@nyu.edu', email='study@nyu.edu', password='study-test-password')
        self.other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu')
        self.client.force_login(self.user)
        self.course = Course.objects.create(owner=self.user, name='Software Engineering', code='CS-GY 6063', semester='Fall 2026')
        self.assignment = Assignment.objects.create(course=self.course, title='Sprint retrospective')

    def session(self, start, end, assignment=None):
        return StudySession.objects.create(assignment=assignment or self.assignment, starts_at=instant(start), ends_at=instant(end))


class AvailabilityTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('study:availability')

    def save(self, blocks):
        return self.client.put(self.url, json.dumps({'blocks': blocks}), content_type='application/json')

    def block(self, weekday=0, start='09:00', end='11:00', **extra):
        return {'weekday': weekday, 'start_time': start, 'end_time': end, **extra}

    def test_empty_availability_exposes_unconfigured_state(self):
        self.assertEqual(self.client.get(self.url).json(), {'timezone': 'UTC', 'configured': False, 'blocks': []})
        self.assertFalse(self.client.get(reverse('study:calendar')).json()['availability_configured'])

    def test_save_all_days_multiple_blocks_and_refresh(self):
        blocks = [self.block(day) for day in range(7)] + [self.block(0, '14:00', '15:30')]
        response = self.save(blocks)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['configured'])
        self.assertEqual(AvailabilityBlock.objects.filter(owner=self.user).count(), 8)
        for _ in range(2):
            payload = self.client.get(self.url).json()
            self.assertEqual(payload, response.json())
            self.assertEqual(payload['blocks'][1], self.block(0, '14:00', '15:30'))

    def test_update_replaces_future_availability_without_changing_sessions(self):
        session = self.session('2026-10-23T12:00', '2026-10-23T13:00')
        self.save([self.block()])
        updated = [self.block(4, '16:00', '18:00')]
        self.assertEqual(self.save(updated).status_code, 200)
        self.assertEqual(self.client.get(self.url).json()['blocks'], updated)
        session.refresh_from_db()
        self.assertEqual(session.starts_at, instant('2026-10-23T12:00'))
        self.assertEqual(StudySession.objects.count(), 1)

    def test_clear_blocks_returns_to_unconfigured_state(self):
        self.save([self.block()])
        response = self.save([])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['configured'])
        self.assertEqual(self.client.get(self.url).json()['blocks'], [])

    def test_invalid_blocks_do_not_replace_saved_availability(self):
        original = [self.block()]
        self.save(original)
        for invalid in [
            self.block(-1), self.block(7), self.block(None),
            self.block(start='not-a-time'), self.block(end='25:00'),
            self.block(start=''), self.block(end=''),
            self.block(start=[]), self.block(end={'time': '10:00'}),
            self.block(True), self.block('Monday'),
            self.block(start='10:00', end='09:00'),
            self.block(start='10:00', end='10:00'),
            {'weekday': 0},
        ]:
            with self.subTest(block=invalid):
                response = self.save([self.block(1), invalid])
                self.assertEqual(response.status_code, 400)
                self.assertIn('1', response.json()['errors'])
                self.assertEqual(self.client.get(self.url).json()['blocks'], original)

    def test_overlap_and_duplicate_are_rejected_but_adjacent_blocks_are_allowed(self):
        for blocks in [
            [self.block(), self.block(0, '10:00', '12:00')],
            [self.block(), self.block()],
            [self.block(0, '08:00', '15:00'), self.block(0, '10:00', '11:00')],
        ]:
            with self.subTest(blocks=blocks):
                self.assertEqual(self.save(blocks).status_code, 400)
        blocks = [self.block(), self.block(0, '11:00', '12:00'), self.block(1)]
        self.assertEqual(self.save(blocks).status_code, 200)

    def test_malformed_payloads_return_400(self):
        for body in ['invalid', '[]', 'null', '{}', '{"blocks": {}}', '{"blocks": [null]}']:
            with self.subTest(body=body):
                response = self.client.put(self.url, body, content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertFalse(AvailabilityBlock.objects.exists())

    def test_ownership_cannot_be_overridden_and_accounts_are_isolated(self):
        self.save([self.block(owner=self.other.pk)])
        self.assertEqual(AvailabilityBlock.objects.get().owner, self.user)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).json()['blocks'], [])
        self.save([self.block(6, '18:00', '19:00')])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).json()['blocks'], [self.block()])

    def test_unauthenticated_requests_cannot_read_or_write(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.save([self.block()]).status_code, 401)
        self.assertFalse(AvailabilityBlock.objects.exists())

    def test_write_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.put(self.url, json.dumps({'blocks': [self.block()]}), content_type='application/json').status_code, 403)
        client.get(reverse('api:session'))
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.put(self.url, json.dumps({'blocks': [self.block()]}), content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 200)


class CalendarTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('study:calendar')

    def week(self, value='2026-10-23'):
        return self.client.get(self.url, {'week': value})

    @patch('apps.study.views.timezone.now', return_value=instant('2026-10-25T23:30'))
    def test_default_week_uses_utc_and_monday_start(self, mock_now):
        with timezone.override('Asia/Tokyo'):
            response = self.client.get(self.url)
        payload = response.json()
        self.assertEqual(payload['week_start'], '2026-10-19')
        self.assertEqual(payload['week_end'], '2026-10-26')
        self.assertEqual(payload['timezone'], 'UTC')

    def test_week_contains_course_task_time_and_sorts_sessions(self):
        later = self.session('2026-10-23T15:00', '2026-10-23T16:30')
        earlier = self.session('2026-10-20T09:00', '2026-10-20T10:00')
        response = self.week()
        self.assertEqual(response.status_code, 200)
        entries = response.json()['sessions']
        self.assertEqual([entry['id'] for entry in entries], [earlier.pk, later.pk])
        self.assertEqual(entries[0]['assignment'], {'id': self.assignment.pk, 'title': 'Sprint retrospective'})
        self.assertEqual(entries[0]['course']['name'], self.course.name)
        self.assertEqual(entries[0]['starts_at'], '2026-10-20T09:00:00+00:00')
        self.assertEqual(entries[0]['ends_at'], '2026-10-20T10:00:00+00:00')
        self.assertEqual(self.week().json(), response.json())

    def test_week_navigation_across_year_boundary(self):
        payload = self.week('2027-01-01').json()
        self.assertEqual(payload['week_start'], '2026-12-28')
        self.assertEqual(payload['previous_week'], '2026-12-21')
        self.assertEqual(payload['next_week'], '2027-01-04')
        self.assertEqual(self.week(payload['next_week']).json()['previous_week'], payload['week_start'])

    def test_week_boundaries_include_overlapping_sessions_only(self):
        self.session('2026-10-18T23:00', '2026-10-19T00:00')
        crossing_start = self.session('2026-10-18T23:00', '2026-10-19T01:00')
        crossing_end = self.session('2026-10-25T23:00', '2026-10-26T01:00')
        self.session('2026-10-26T00:00', '2026-10-26T01:00')
        self.assertEqual([s['id'] for s in self.week().json()['sessions']], [crossing_start.pk, crossing_end.pk])

    def test_other_weeks_have_empty_lists(self):
        self.session('2026-10-23T15:00', '2026-10-23T16:00')
        self.assertEqual(self.week('2026-11-02').json()['sessions'], [])

    def test_only_own_sessions_are_visible(self):
        mine = self.session('2026-10-23T15:00', '2026-10-23T16:00')
        other_course = Course.objects.create(owner=self.other, name='Private', semester='Fall 2026')
        other_task = Assignment.objects.create(course=other_course, title='Private task')
        self.session('2026-10-23T17:00', '2026-10-23T18:00', assignment=other_task)
        response = self.week()
        self.assertEqual([s['id'] for s in response.json()['sessions']], [mine.pk])
        self.assertNotContains(response, 'Private')

    def test_invalid_week_returns_clear_error(self):
        for value in ['invalid', '2026-02-30', '', '0001-01-01', '9999-12-31']:
            with self.subTest(value=value):
                response = self.week(value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('YYYY-MM-DD', response.json()['detail'])

    def test_unauthenticated_calendar_is_private(self):
        self.client.logout()
        self.assertEqual(self.week().status_code, 401)

    def test_calendar_is_read_only(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_invalid_session_duration_is_rejected(self):
        session = StudySession(assignment=self.assignment, starts_at=instant('2026-10-23T16:00'), ends_at=instant('2026-10-23T15:00'))
        with self.assertRaises(ValidationError):
            session.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            session.save()
