import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.coursework.models import Assignment, Course
from apps.study.models import StudySession


class NotificationPreferencesApiTests(TestCase):
    """#37: a student chooses whether and how early study reminders appear."""

    def setUp(self):
        self.user = User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='test123')
        self.url = reverse('api:profile_notifications')

    def put(self, body):
        return self.client.put(self.url, json.dumps(body), content_type='application/json')

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.put({'study_reminders_enabled': False}).status_code, 401)

    def test_only_get_and_put_are_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_defaults_match_how_reminders_worked_before(self):
        self.client.force_login(self.user)
        settings = self.client.get(self.url).json()['notifications']
        self.assertEqual(settings, {'study_reminders_enabled': True, 'study_reminder_minutes': 60})

    def test_the_server_says_which_lead_times_are_allowed(self):
        self.client.force_login(self.user)
        expected = {'study_reminder_minutes': [15, 30, 60, 120]}
        self.assertEqual(self.client.get(self.url).json()['options'], expected)
        self.assertEqual(self.put({'study_reminders_enabled': False}).json()['options'], expected)

    def test_turn_reminders_off_and_on(self):
        self.client.force_login(self.user)
        self.assertFalse(self.put({'study_reminders_enabled': False}).json()['notifications']['study_reminders_enabled'])
        self.user.refresh_from_db()
        self.assertFalse(self.user.study_reminders_enabled)
        self.assertTrue(self.put({'study_reminders_enabled': True}).json()['notifications']['study_reminders_enabled'])

    def test_every_offered_lead_time_can_be_saved(self):
        self.client.force_login(self.user)
        for minutes in (15, 30, 60, 120):
            response = self.put({'study_reminder_minutes': minutes})
            self.assertEqual(response.status_code, 200, minutes)
            self.assertEqual(response.json()['notifications']['study_reminder_minutes'], minutes)
            self.user.refresh_from_db()
            self.assertEqual(self.user.study_reminder_minutes, minutes)

    def test_a_setting_left_out_keeps_its_current_value(self):
        self.user.study_reminders_enabled = False
        self.user.study_reminder_minutes = 15
        self.user.save()
        self.client.force_login(self.user)
        settings = self.put({'study_reminder_minutes': 30}).json()['notifications']
        self.assertEqual(settings, {'study_reminders_enabled': False, 'study_reminder_minutes': 30})

    def test_settings_persist_across_requests(self):
        self.client.force_login(self.user)
        self.put({'study_reminders_enabled': False, 'study_reminder_minutes': 120})
        self.assertEqual(
            self.client.get(self.url).json()['notifications'],
            {'study_reminders_enabled': False, 'study_reminder_minutes': 120},
        )

    def test_rejects_an_on_off_value_that_is_not_true_or_false(self):
        self.client.force_login(self.user)
        for bad in ('false', 'yes', 0, 1, None, []):
            response = self.put({'study_reminders_enabled': bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('study_reminders_enabled', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.study_reminders_enabled)

    def test_rejects_a_lead_time_that_is_not_one_of_the_choices(self):
        self.client.force_login(self.user)
        for bad in (0, 10, 45, 90, 121, -15, '60', 60.5, True, None, [60]):
            response = self.put({'study_reminder_minutes': bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('study_reminder_minutes', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.study_reminder_minutes, 60)

    def test_a_bad_value_changes_nothing(self):
        self.client.force_login(self.user)
        response = self.put({'study_reminders_enabled': False, 'study_reminder_minutes': 45})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.study_reminders_enabled)

    def test_rejects_malformed_json_and_non_objects(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.put(self.url, '{nope', content_type='application/json').status_code, 400)
        self.assertEqual(self.put([True]).status_code, 400)

    def test_only_changes_the_signed_in_students_own_settings(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='test123')
        self.client.force_login(self.user)
        self.put({'study_reminders_enabled': False, 'user': other.pk, 'id': other.pk})
        other.refresh_from_db()
        self.assertTrue(other.study_reminders_enabled)

    def test_does_not_touch_the_profile(self):
        self.user.first_name, self.user.bio = 'Jane', 'Hello'
        self.user.save()
        self.client.force_login(self.user)
        self.put({'study_reminders_enabled': False, 'first_name': 'Hacker', 'bio': 'changed'})
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.bio), ('Jane', 'Hello'))


class ReminderPreferencesAffectDashboardTests(TestCase):
    """#37: the dashboard's reminders follow the student's own settings."""

    def setUp(self):
        self.user = User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='test123')
        self.client.force_login(self.user)
        self.now = timezone.now()
        course = Course.objects.create(owner=self.user, name='Software Engineering', code='CS-GY 6063', semester='Fall 2026')
        self.assignment = Assignment.objects.create(course=course, title='Sprint review')

    def session(self, starts_in, assignment=None):
        starts_at = self.now + starts_in
        return StudySession.objects.create(
            assignment=assignment or self.assignment, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30),
        )

    def reminders(self, client=None):
        with mock.patch('apps.api.views.timezone.now', return_value=self.now):
            return (client or self.client).get(reverse('api:dashboard')).json()['study_reminders']

    def configure(self, **fields):
        for name, value in fields.items():
            setattr(self.user, name, value)
        self.user.save()

    def test_default_is_still_one_hour_ahead(self):
        within = self.session(timedelta(minutes=59))
        self.session(timedelta(minutes=61))
        self.assertEqual([item['id'] for item in self.reminders()], [within.pk])

    def test_turning_reminders_off_removes_them_from_the_dashboard(self):
        self.session(timedelta(minutes=10))
        self.assertEqual(len(self.reminders()), 1)
        self.configure(study_reminders_enabled=False)
        self.assertEqual(self.reminders(), [])

    def test_turning_reminders_back_on_brings_them_back(self):
        self.session(timedelta(minutes=10))
        self.configure(study_reminders_enabled=False)
        self.configure(study_reminders_enabled=True)
        self.assertEqual(len(self.reminders()), 1)

    def test_a_shorter_lead_time_only_reminds_closer_to_the_session(self):
        self.configure(study_reminder_minutes=15)
        soon = self.session(timedelta(minutes=10))
        self.session(timedelta(minutes=20))
        self.assertEqual([item['id'] for item in self.reminders()], [soon.pk])

    def test_a_longer_lead_time_reminds_earlier(self):
        self.configure(study_reminder_minutes=120)
        far = self.session(timedelta(minutes=110))
        self.session(timedelta(minutes=125))
        self.assertEqual([item['id'] for item in self.reminders()], [far.pk])

    def test_the_window_edge_is_inclusive_and_the_past_never_counts(self):
        self.configure(study_reminder_minutes=30)
        edge = self.session(timedelta(minutes=30))
        self.session(timedelta(minutes=30, seconds=1))
        self.session(timedelta(seconds=-1))
        self.assertEqual([item['id'] for item in self.reminders()], [edge.pk])

    def test_one_students_settings_do_not_change_another_students_reminders(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='test123')
        other_course = Course.objects.create(owner=other, name='Algorithms', code='CS-GY 6033', semester='Fall 2026')
        other_assignment = Assignment.objects.create(course=other_course, title='Problem set')
        self.configure(study_reminders_enabled=False)
        self.session(timedelta(minutes=10))
        theirs = self.session(timedelta(minutes=10), assignment=other_assignment)
        self.client.force_login(other)
        self.assertEqual([item['id'] for item in self.reminders()], [theirs.pk])
