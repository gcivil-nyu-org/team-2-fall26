import json
from datetime import time

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.coursework.models import Assignment, Course
from .models import AvailabilityBlock, StudySession
from .services import replace_unlocked_sessions
from .tests import StudyTestCase, instant


class SessionControlTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.session('2026-11-02T09:00', '2026-11-02T10:00')
        self.url = reverse('study:session', args=[self.entry.pk])
        AvailabilityBlock.objects.create(owner=self.user, weekday=0, start_time=time(9), end_time=time(12))
        other_course = Course.objects.create(owner=self.other, name='Private', semester='Fall')
        self.other_task = Assignment.objects.create(course=other_course, title='Private')
        self.other_entry = self.session('2026-11-02T10:00', '2026-11-02T11:00', self.other_task)

    def update(self, body, client=None):
        return (client or self.client).patch(self.url, json.dumps(body), content_type='application/json')

    def move(self, start='2026-11-02T10:00', end='2026-11-02T11:00', **extra):
        return self.update({'starts_at': start, 'ends_at': end, **extra})

    def test_lock_unlock_and_calendar_persistence(self):
        for locked in [True, False]:
            response = self.update({'is_locked': locked})
            self.assertEqual(response.status_code, 200)
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.is_locked, locked)
            entry = self.client.get(reverse('study:calendar'), {'week': '2026-11-02'}).json()['sessions'][0]
            self.assertEqual(entry['is_locked'], locked)
        self.other_entry.refresh_from_db()
        self.assertFalse(self.other_entry.is_locked)

    def test_move_persists_without_affecting_other_sessions_or_lock(self):
        self.entry.is_locked = True
        self.entry.save()
        with timezone.override('America/New_York'):
            response = self.move()
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T10:00'))
        self.assertTrue(self.entry.is_locked)
        entries = self.client.get(reverse('study:calendar'), {'week': '2026-11-02'}).json()['sessions']
        self.assertEqual(entries[0]['starts_at'], '2026-11-02T10:00:00+00:00')
        self.other_entry.refresh_from_db()
        self.assertEqual(self.other_entry.starts_at, instant('2026-11-02T10:00'))
        self.assertEqual(StudySession.objects.count(), 2)

    def test_overlap_warns_then_allows_explicit_confirmation(self):
        other = self.session('2026-11-02T10:30', '2026-11-02T11:30')
        response = self.move()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['warnings'], ['This time overlaps another study session.'])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T09:00'))
        self.assertEqual(self.move(confirm_warnings=True).status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.starts_at, instant('2026-11-02T10:30'))

    def test_outside_availability_and_missing_availability_warn(self):
        for configured in [True, False]:
            if not configured:
                AvailabilityBlock.objects.all().delete()
            response = self.move('2026-11-03T10:00', '2026-11-03T11:00')
            self.assertEqual(response.status_code, 409)
            self.assertIn('availability', response.json()['warnings'][0])
        self.assertEqual(self.move('2026-11-03T10:00', '2026-11-03T11:00', confirm_warnings=True).status_code, 200)

    def test_both_warnings_return_together_and_combined_lock_is_atomic(self):
        self.session('2026-11-03T10:00', '2026-11-03T12:00')
        response = self.move('2026-11-03T10:00', '2026-11-03T11:00', is_locked=True)
        self.assertEqual(len(response.json()['warnings']), 2)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_locked)
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T09:00'))

    def test_availability_boundaries_adjacent_blocks_and_gaps(self):
        AvailabilityBlock.objects.create(owner=self.user, weekday=0, start_time=time(12), end_time=time(13))
        self.assertEqual(self.move('2026-11-02T11:00', '2026-11-02T13:00').status_code, 200)
        self.assertEqual(self.move('2026-11-02T12:00', '2026-11-02T13:01').status_code, 409)
        AvailabilityBlock.objects.filter(start_time=time(12)).update(start_time=time(12, 30))
        self.assertEqual(self.move('2026-11-02T11:00', '2026-11-02T13:00').status_code, 409)

    def test_overnight_move_warns_and_can_be_confirmed(self):
        self.assertEqual(self.move('2026-11-02T23:30', '2026-11-03T00:30').status_code, 409)
        self.assertEqual(self.move('2026-11-02T23:30', '2026-11-03T00:30', confirm_warnings=True).status_code, 200)

    def test_explicit_offsets_preserve_instant(self):
        self.assertEqual(self.move('2026-11-02T05:00:00-05:00', '2026-11-02T06:00:00-05:00').status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T10:00'))

    def test_moving_to_another_week_updates_both_weeks(self):
        self.assertEqual(self.move('2026-11-09T10:00', '2026-11-09T11:00').status_code, 200)
        self.assertEqual(self.client.get(reverse('study:calendar'), {'week': '2026-11-02'}).json()['sessions'], [])
        self.assertEqual(self.client.get(reverse('study:calendar'), {'week': '2026-11-09'}).json()['sessions'][0]['id'], self.entry.pk)

    def test_invalid_input_cannot_move_or_lock_session(self):
        for body in [
            {}, [], None, {'is_locked': 'true'}, {'is_locked': 1}, {'confirm_warnings': True},
            {'starts_at': 'invalid', 'ends_at': '2026-11-02T11:00'},
            {'starts_at': '2026-11-02T10:00'}, {'starts_at': [], 'ends_at': True},
            {'starts_at': '2026-11-02T11:00', 'ends_at': '2026-11-02T10:00'},
            {'starts_at': '2026-11-02T10:00', 'ends_at': '2026-11-02T10:00'},
            {'starts_at': '2026-11-02T10:00', 'ends_at': '2026-11-02T11:00', 'confirm_warnings': 'true'},
            {'is_locked': True, 'owner': self.other.pk},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.update(body).status_code, 400)
        self.assertEqual(self.client.patch(self.url, 'invalid', content_type='application/json').status_code, 400)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_locked)
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T09:00'))

    def test_other_accounts_and_missing_sessions_are_inaccessible(self):
        self.client.force_login(self.other)
        self.assertEqual(self.update({'is_locked': True}).status_code, 404)
        self.assertEqual(self.move().status_code, 404)
        self.assertEqual(self.client.patch(reverse('study:session', args=[999999]), '{"is_locked": true}', content_type='application/json').status_code, 404)
        self.client.logout()
        self.assertEqual(self.update({'is_locked': True}).status_code, 401)

    def test_methods_and_csrf_protect_writes(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self.update({'is_locked': True}, client).status_code, 403)
        client.get(reverse('api:session'))
        response = client.patch(self.url, json.dumps({'is_locked': True}), content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)

    def test_regeneration_replaces_unlocked_only_and_unlock_restores_replacement(self):
        self.update({'is_locked': True})
        old = self.session('2026-11-02T11:00', '2026-11-02T12:00')
        outside = self.session('2026-11-09T11:00', '2026-11-09T12:00')
        def candidate():
            return StudySession(assignment=self.assignment, starts_at=instant('2026-11-02T10:00'), ends_at=instant('2026-11-02T11:00'))
        replace_unlocked_sessions(self.user, instant('2026-11-02T00:00'), instant('2026-11-09T00:00'), [candidate()])
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_locked)
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T09:00'))
        self.assertFalse(StudySession.objects.filter(pk=old.pk).exists())
        self.assertTrue(StudySession.objects.filter(pk=outside.pk).exists())
        self.assertTrue(StudySession.objects.filter(pk=self.other_entry.pk).exists())
        self.update({'is_locked': False})
        replace_unlocked_sessions(self.user, instant('2026-11-02T00:00'), instant('2026-11-09T00:00'), [candidate()])
        self.assertFalse(StudySession.objects.filter(pk=self.entry.pk).exists())

    def test_bad_generation_plan_rolls_back_and_preserves_locked_sessions(self):
        self.update({'is_locked': True})
        old = self.session('2026-11-02T11:00', '2026-11-02T12:00')
        for task, start, end in [
            (self.assignment, '2026-11-02T09:30', '2026-11-02T10:30'),
            (self.other_task, '2026-11-02T10:00', '2026-11-02T11:00'),
            (self.assignment, '2026-11-10T10:00', '2026-11-10T11:00'),
        ]:
            with self.subTest(task=task, start=start), self.assertRaises(ValidationError):
                replace_unlocked_sessions(self.user, instant('2026-11-02T00:00'), instant('2026-11-09T00:00'), [StudySession(assignment=task, starts_at=instant(start), ends_at=instant(end))])
        self.assertTrue(StudySession.objects.filter(pk=old.pk).exists())
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_locked)
