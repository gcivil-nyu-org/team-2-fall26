import json
from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.coursework.models import Assignment, Course, Exam
from .models import AvailabilityBlock, StudySession
from .services import preserved_sessions, replace_unlocked_sessions
from .tests import StudyTestCase, instant


class SessionControlTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.session('2026-11-02T09:00', '2026-11-02T10:00')
        self.url = reverse('study:session', args=[self.entry.pk])
        AvailabilityBlock.objects.create(owner=self.user, weekday=0, start_time=time(4), end_time=time(7))
        other_course = Course.objects.create(owner=self.other, name='Private', semester='Fall')
        self.other_task = Assignment.objects.create(course=other_course, title='Private')
        self.other_entry = self.session('2026-11-02T10:00', '2026-11-02T11:00', self.other_task)

    def update(self, body, client=None):
        return (client or self.client).patch(self.url, json.dumps(body), content_type='application/json')

    def move(self, start='2026-11-02T05:00', end='2026-11-02T06:00', **extra):
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
        response = self.move('2026-11-03T05:00', '2026-11-03T06:00', is_locked=True)
        self.assertEqual(len(response.json()['warnings']), 2)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_locked)
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T09:00'))

    def test_availability_boundaries_adjacent_blocks_and_gaps(self):
        AvailabilityBlock.objects.create(owner=self.user, weekday=0, start_time=time(7), end_time=time(8))
        self.assertEqual(self.move('2026-11-02T06:00', '2026-11-02T08:00').status_code, 200)
        self.assertEqual(self.move('2026-11-02T07:00', '2026-11-02T08:01').status_code, 409)
        AvailabilityBlock.objects.filter(start_time=time(7)).update(start_time=time(7, 30))
        self.assertEqual(self.move('2026-11-02T06:00', '2026-11-02T08:00').status_code, 409)

    def test_overnight_move_warns_and_can_be_confirmed(self):
        self.assertEqual(self.move('2026-11-02T23:30', '2026-11-03T00:30').status_code, 409)
        self.assertEqual(self.move('2026-11-02T23:30', '2026-11-03T00:30', confirm_warnings=True).status_code, 200)

    def test_explicit_offsets_preserve_instant(self):
        self.assertEqual(self.move('2026-11-02T05:00:00-05:00', '2026-11-02T06:00:00-05:00').status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.starts_at, instant('2026-11-02T10:00'))

    def test_moving_to_another_week_updates_both_weeks(self):
        self.assertEqual(self.move('2026-11-09T05:00', '2026-11-09T06:00').status_code, 200)
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

    def test_preserved_helper_and_replacement_agree_on_boundaries_and_ownership(self):
        start, end = instant('2026-11-02T00:00'), instant('2026-11-09T00:00')
        self.update({'is_locked': True})
        crosses_start = self.session('2026-11-01T23:30', '2026-11-02T00:30')
        crosses_end = self.session('2026-11-08T23:30', '2026-11-09T00:30')
        before = self.session('2026-11-01T23:00', '2026-11-02T00:00')
        after = self.session('2026-11-09T00:00', '2026-11-09T01:00')
        exact_start = self.session('2026-11-02T00:00', '2026-11-02T01:00')
        exact_end = self.session('2026-11-08T23:00', '2026-11-09T00:00')
        expected = {self.entry.pk, crosses_start.pk, crosses_end.pk, before.pk, after.pk}
        self.assertSetEqual(set(preserved_sessions(self.user, start, end).values_list('pk', flat=True)), expected)
        self.assertSetEqual(set(preserved_sessions(self.other, start, end).values_list('pk', flat=True)), set())
        replace_unlocked_sessions(self.user, start, end, [])
        self.assertSetEqual(set(StudySession.objects.filter(assignment__course__owner=self.user).values_list('pk', flat=True)), expected)
        self.assertFalse(StudySession.objects.filter(pk__in=[exact_start.pk, exact_end.pk]).exists())
        self.assertTrue(StudySession.objects.filter(pk=self.other_entry.pk).exists())

    def test_generator_cannot_place_sessions_over_a_preserved_boundary_session(self):
        boundary = self.session('2026-11-01T23:30', '2026-11-02T00:30')
        candidate = StudySession(assignment=self.assignment, starts_at=instant('2026-11-02T00:00'), ends_at=instant('2026-11-02T01:00'))
        with self.assertRaises(ValidationError):
            replace_unlocked_sessions(self.user, instant('2026-11-02T00:00'), instant('2026-11-09T00:00'), [candidate])
        self.assertTrue(StudySession.objects.filter(pk=boundary.pk).exists())
        self.assertTrue(StudySession.objects.filter(pk=self.entry.pk).exists())

    def test_preservation_and_replacement_reject_invalid_windows_without_changes(self):
        start = instant('2026-11-02T00:00')
        for end in [start, instant('2026-11-01T00:00')]:
            with self.subTest(end=end):
                with self.assertRaises(ValidationError):
                    preserved_sessions(self.user, start, end)
                with self.assertRaises(ValidationError):
                    replace_unlocked_sessions(self.user, start, end, [])
        self.assertEqual(StudySession.objects.count(), 2)


class ExamSessionTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.exam = Exam.objects.create(course=self.course, title='Midterm', starts_at=instant('2026-11-12T19:00'))
        self.entry = StudySession.objects.create(exam=self.exam, starts_at=instant('2026-11-10T14:00'), ends_at=instant('2026-11-10T15:00'))

    def test_exam_sessions_show_on_the_calendar_with_their_course(self):
        entry = self.client.get(reverse('study:calendar'), {'week': '2026-11-09'}).json()['sessions'][0]
        self.assertEqual(entry['exam'], {'id': self.exam.pk, 'title': 'Midterm'})
        self.assertIsNone(entry['assignment'])
        self.assertEqual(entry['course']['code'], 'CS-GY 6063')

    def test_exam_sessions_can_be_locked_and_moved(self):
        url = reverse('study:session', args=[self.entry.pk])
        response = self.client.patch(url, json.dumps({'is_locked': True}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(url, json.dumps({'starts_at': '2026-11-10T11:00', 'ends_at': '2026-11-10T12:00',
                                                      'confirm_warnings': True}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_locked)
        self.assertEqual(self.entry.ends_at - self.entry.starts_at, timedelta(hours=1))

    def test_other_students_cannot_see_or_change_exam_sessions(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('study:calendar'), {'week': '2026-11-09'}).json()['sessions'], [])
        response = self.client.patch(reverse('study:session', args=[self.entry.pk]), json.dumps({'is_locked': True}),
                                     content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(preserved_sessions(self.other, instant('2026-11-01T00:00'), instant('2026-12-01T00:00')).exists())

    def test_a_session_belongs_to_exactly_one_assignment_or_exam(self):
        both = StudySession(assignment=self.assignment, exam=self.exam, starts_at=instant('2026-11-10T16:00'), ends_at=instant('2026-11-10T17:00'))
        neither = StudySession(starts_at=instant('2026-11-10T16:00'), ends_at=instant('2026-11-10T17:00'))
        for session in (both, neither):
            with self.assertRaises(ValidationError):
                session.full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                session.save()

    def test_deleting_the_exam_removes_its_sessions(self):
        self.exam.delete()
        self.assertFalse(StudySession.objects.filter(pk=self.entry.pk).exists())


class SessionCompletionTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.session('2026-11-02T14:00', '2026-11-02T15:00')
        self.url = reverse('study:session', args=[self.entry.pk])

    def update(self, body):
        return self.client.patch(self.url, json.dumps(body), content_type='application/json')

    def calendar_entry(self):
        return self.client.get(reverse('study:calendar'), {'week': '2026-11-02'}).json()['sessions'][0]

    def test_complete_and_reopen_persist_on_the_calendar(self):
        self.assertFalse(self.calendar_entry()['is_complete'])
        for complete in [True, False]:
            response = self.update({'is_complete': complete})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['is_complete'], complete)
            self.entry.refresh_from_db()
            self.assertEqual(self.entry.is_complete, complete)
            self.assertEqual(self.calendar_entry()['is_complete'], complete)

    def test_completion_leaves_time_and_lock_alone(self):
        self.entry.is_locked = True
        self.entry.save()
        self.update({'is_complete': True})
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_locked)
        self.assertEqual((self.entry.starts_at, self.entry.ends_at), (instant('2026-11-02T14:00'), instant('2026-11-02T15:00')))

    def test_invalid_completion_values_are_rejected(self):
        for value in ['yes', 1, None]:
            response = self.update({'is_complete': value})
            self.assertEqual(response.status_code, 400)
            self.assertIn('is_complete', response.json()['errors'])
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_complete)

    def test_other_students_cannot_complete_my_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.update({'is_complete': True}).status_code, 404)
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.is_complete)

    def test_completed_sessions_are_never_replaced_by_regeneration(self):
        done = StudySession.objects.create(assignment=self.assignment, is_complete=True,
                                           starts_at=instant('2026-11-03T14:00'), ends_at=instant('2026-11-03T15:00'))
        window = (instant('2026-11-03T00:00'), instant('2026-11-04T00:00'))
        self.assertIn(done, preserved_sessions(self.user, *window))
        replace_unlocked_sessions(self.user, *window, [])
        self.assertTrue(StudySession.objects.filter(pk=done.pk).exists())
        candidate = StudySession(assignment=self.assignment, is_complete=True,
                                 starts_at=instant('2026-11-03T16:00'), ends_at=instant('2026-11-03T17:00'))
        with self.assertRaises(ValidationError):
            replace_unlocked_sessions(self.user, *window, [candidate])



class RemoveSessionTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.session('2026-11-02T14:00', '2026-11-02T15:00')
        self.neighbour = self.session('2026-11-02T16:00', '2026-11-02T17:00')
        self.url = reverse('study:session', args=[self.entry.pk])

    def calendar_ids(self):
        return [item['id'] for item in self.client.get(reverse('study:calendar'), {'week': '2026-11-02'}).json()['sessions']]

    def test_removing_a_session_keeps_everything_else(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudySession.objects.filter(pk=self.entry.pk).exists())
        self.assertEqual(self.calendar_ids(), [self.neighbour.pk])
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_locked_and_exam_sessions_can_be_removed(self):
        self.entry.is_locked = True
        self.entry.save()
        exam = Exam.objects.create(course=self.course, title='Midterm', starts_at=instant('2026-11-12T19:00'))
        prep = StudySession.objects.create(exam=exam, starts_at=instant('2026-11-03T14:00'), ends_at=instant('2026-11-03T15:00'))
        self.assertEqual(self.client.delete(self.url).status_code, 200)
        self.assertEqual(self.client.delete(reverse('study:session', args=[prep.pk])).status_code, 200)
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())
        self.assertEqual(self.calendar_ids(), [self.neighbour.pk])

    def test_other_students_cannot_remove_my_session(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertTrue(StudySession.objects.filter(pk=self.entry.pk).exists())

    def test_removing_needs_login_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.delete(self.url).status_code, 401)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.delete(self.url).status_code, 403)
        self.assertTrue(StudySession.objects.filter(pk=self.entry.pk).exists())

    def test_a_removed_session_is_gone_for_good(self):
        self.client.delete(self.url)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
