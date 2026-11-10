from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import Client
from django.urls import reverse

from apps.coursework.models import Assignment, Course, Exam
from .models import AvailabilityBlock, ClassMeeting, StudySession
from .planner import generate_study_plan
from .services import NYU_TIME
from .tests import StudyTestCase

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=NYU_TIME)  # Monday


def eastern(value):
    return datetime.fromisoformat(value).replace(tzinfo=NYU_TIME)


class GenerateStudyPlanTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('study:generate')
        # The shared fixture's assignment has no deadline; keep it out of these plans.
        self.assignment.mark_complete()
        for weekday in (0, 1, 2):  # Monday–Wednesday, 9:00–13:00 Eastern
            AvailabilityBlock.objects.create(owner=self.user, weekday=weekday, start_time=time(9), end_time=time(13))

    def task(self, title, due, hours, **extra):
        return Assignment.objects.create(
            course=self.course, title=title, due_date=eastern(due) if due else None,
            estimated_workload=Decimal(str(hours)) if hours is not None else None, **extra,
        )

    def generate(self, client=None):
        with patch('apps.study.planner.timezone.now', return_value=NOW):
            return (client or self.client).post(self.url)

    def exam(self, title, starts, hours, **extra):
        return Exam.objects.create(
            course=self.course, title=title, starts_at=eastern(starts),
            estimated_workload=Decimal(str(hours)) if hours is not None else None, **extra,
        )

    def times(self, item):
        field = 'exam' if isinstance(item, Exam) else 'assignment'
        return [(session.starts_at.astimezone(NYU_TIME).strftime('%a %H:%M'), session.ends_at.astimezone(NYU_TIME).strftime('%H:%M'))
                for session in StudySession.objects.filter(**{field: item})]

    def test_workload_is_split_into_sessions_of_at_most_two_hours_inside_availability(self):
        essay = self.task('Essay', '2026-11-11T23:59', 3)
        response = self.generate()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.times(essay), [('Mon 09:00', '11:00'), ('Mon 11:15', '12:15')])

    def test_sooner_deadlines_are_planned_first_and_before_they_are_due(self):
        essay = self.task('Essay', '2026-11-11T23:59', 3)
        report = self.task('Report', '2026-11-10T12:00', 2)
        self.generate()
        self.assertEqual(self.times(report), [('Mon 09:00', '11:00')])
        self.assertEqual(self.times(essay), [('Mon 11:15', '13:00'), ('Tue 09:00', '10:15')])

    def test_priority_breaks_ties_between_equal_deadlines(self):
        low = self.task('Low', '2026-11-11T23:59', 1, priority='low')
        high = self.task('High', '2026-11-11T23:59', 1, priority='high')
        self.generate()
        self.assertEqual(self.times(high), [('Mon 09:00', '10:00')])
        self.assertEqual(self.times(low), [('Mon 10:15', '11:15')])

    def test_sessions_never_land_after_the_deadline(self):
        task = self.task('Quiz prep', '2026-11-09T10:30', 4)
        self.generate()
        self.assertEqual(self.times(task), [('Mon 09:00', '10:30')])

    def test_locked_sessions_are_kept_and_count_toward_the_workload(self):
        essay = self.task('Essay', '2026-11-11T23:59', 3)
        locked = StudySession.objects.create(assignment=essay, is_locked=True,
                                             starts_at=eastern('2026-11-09T09:00'), ends_at=eastern('2026-11-09T10:00'))
        self.generate()
        locked.refresh_from_db()
        self.assertTrue(locked.is_locked)
        self.assertEqual((locked.starts_at, locked.ends_at), (eastern('2026-11-09T09:00'), eastern('2026-11-09T10:00')))
        self.assertEqual(self.times(essay), [('Mon 09:00', '10:00'), ('Mon 10:00', '12:00')])

    def test_unlocked_upcoming_sessions_are_replaced_but_past_ones_are_kept(self):
        essay = self.task('Essay', '2026-11-11T23:59', 2)
        past = StudySession.objects.create(assignment=essay, starts_at=eastern('2026-11-06T09:00'), ends_at=eastern('2026-11-06T10:00'))
        stale = StudySession.objects.create(assignment=essay, starts_at=eastern('2026-11-10T18:00'), ends_at=eastern('2026-11-10T19:00'))
        self.generate()
        self.assertTrue(StudySession.objects.filter(pk=past.pk).exists())
        self.assertFalse(StudySession.objects.filter(pk=stale.pk).exists())
        # The past hour counts, so one more hour is planned.
        self.assertEqual(self.times(essay), [('Fri 09:00', '10:00'), ('Mon 09:00', '10:00')])

    def test_class_meetings_are_avoided(self):
        essay = self.task('Essay', '2026-11-11T23:59', 2)
        ClassMeeting.objects.create(course=self.course, term='Fall 2026', source_uid='swe',
                                    starts_at=eastern('2026-11-09T09:15'), ends_at=eastern('2026-11-09T11:00'))
        self.generate()
        self.assertEqual(self.times(essay), [('Mon 11:00', '13:00')])

    def test_not_enough_time_schedules_what_fits_and_reports_the_rest(self):
        report = self.task('Report', '2026-11-09T23:59', 5)
        response = self.generate().json()
        self.assertEqual(self.times(report), [('Mon 09:00', '11:00'), ('Mon 11:15', '13:00')])
        self.assertEqual(len(response['shortfalls']), 1)
        shortfall = response['shortfalls'][0]
        self.assertEqual((shortfall['id'], shortfall['title'], shortfall['hours_short']), (report.pk, 'Report', 1.25))
        self.assertEqual(shortfall['course']['code'], 'CS-GY 6063')

    def test_assignments_that_cannot_be_planned_are_listed_with_a_reason(self):
        self.task('No deadline', None, 2)
        self.task('No estimate', '2026-11-11T23:59', None)
        self.task('Overdue', '2026-11-08T23:59', 2)
        done = self.task('Done', '2026-11-11T23:59', 2)
        done.mark_complete()
        response = self.generate().json()
        reasons = {item['title']: item['reason'] for item in response['skipped']}
        self.assertEqual(set(reasons), {'No deadline', 'No estimate', 'Overdue'})
        self.assertIn('deadline', reasons['No deadline'])
        self.assertIn('workload', reasons['No estimate'])
        self.assertIn('passed', reasons['Overdue'])
        self.assertEqual(response['sessions'], [])

    def test_nothing_to_plan_leaves_existing_sessions_alone(self):
        upcoming = self.session('2026-11-10T15:00', '2026-11-10T16:00')
        self.generate()
        self.assertTrue(StudySession.objects.filter(pk=upcoming.pk).exists())

    def test_generated_sessions_appear_on_the_calendar_immediately(self):
        self.task('Essay', '2026-11-11T23:59', 1)
        created = self.generate().json()['sessions']
        calendar = self.client.get(reverse('study:calendar'), {'week': '2026-11-09'}).json()['sessions']
        self.assertEqual([item['id'] for item in calendar], [item['id'] for item in created])
        self.assertEqual(created[0]['assignment']['title'], 'Essay')
        self.assertFalse(created[0]['is_locked'])

    def test_missing_availability_is_a_clear_error_and_changes_nothing(self):
        AvailabilityBlock.objects.filter(owner=self.user).delete()
        self.task('Essay', '2026-11-11T23:59', 2)
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn('availability', response.json()['detail'])
        self.assertFalse(StudySession.objects.exists())

    def test_other_students_data_is_never_used_or_changed(self):
        other_course = Course.objects.create(owner=self.other, name='Private', semester='Fall 2026')
        theirs = Assignment.objects.create(course=other_course, title='Theirs', due_date=eastern('2026-11-11T23:59'),
                                           estimated_workload=Decimal('2'))
        their_session = StudySession.objects.create(assignment=theirs, starts_at=eastern('2026-11-10T09:00'),
                                                    ends_at=eastern('2026-11-10T10:00'))
        AvailabilityBlock.objects.create(owner=self.other, weekday=0, start_time=time(14), end_time=time(18))
        essay = self.task('Essay', '2026-11-11T23:59', 1)
        response = self.generate().json()
        self.assertEqual([item['id'] for item in response['skipped'] + response['shortfalls']], [])
        self.assertEqual(self.times(essay), [('Mon 09:00', '10:00')])
        self.assertTrue(StudySession.objects.filter(pk=their_session.pk).exists())
        self.assertFalse(StudySession.objects.filter(assignment=theirs).exclude(pk=their_session.pk).exists())

    def test_requires_login_post_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.generate().status_code, 401)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(self.generate(strict).status_code, 403)

    def test_sessions_follow_eastern_time_across_the_dst_change(self):
        spring = datetime(2027, 3, 13, 8, 0, tzinfo=NYU_TIME)  # Saturday before clocks go forward
        AvailabilityBlock.objects.create(owner=self.user, weekday=6, start_time=time(9), end_time=time(10))
        essay = self.task('Essay', '2027-03-14T23:59', 1)
        # Called directly: moving the clock months ahead would expire the test login.
        generate_study_plan(self.user, now=spring)
        session = StudySession.objects.get(assignment=essay)
        self.assertEqual(session.starts_at, datetime(2027, 3, 14, 9, 0, tzinfo=NYU_TIME))
        self.assertEqual(session.ends_at - session.starts_at, timedelta(hours=1))

    def test_exam_prep_is_planned_before_the_exam_starts(self):
        midterm = self.exam('Midterm', '2026-11-10T10:00', 3, priority='high')
        response = self.generate().json()
        self.assertEqual(self.times(midterm), [('Mon 09:00', '11:00'), ('Mon 11:15', '12:15')])
        self.assertEqual(response['sessions'][0]['exam'], {'id': midterm.pk, 'title': 'Midterm'})
        self.assertIsNone(response['sessions'][0]['assignment'])

    def test_exams_and_assignments_share_free_time_in_deadline_order(self):
        essay = self.task('Essay', '2026-11-11T23:59', 2)
        quiz = self.exam('Quiz', '2026-11-10T12:00', 2)
        self.generate()
        self.assertEqual(self.times(quiz), [('Mon 09:00', '11:00')])
        self.assertEqual(self.times(essay), [('Mon 11:15', '13:00'), ('Tue 09:00', '09:15')])

    def test_exam_shortfalls_and_missing_workload_are_reported(self):
        self.exam('No estimate', '2026-11-11T09:00', None)
        final = self.exam('Final', '2026-11-09T12:00', 5)
        self.exam('Last week', '2026-11-02T09:00', 2)
        response = self.generate().json()
        self.assertEqual([(item['kind'], item['title']) for item in response['skipped']], [('exam', 'No estimate')])
        self.assertEqual([(item['kind'], item['title'], item['hours_short']) for item in response['shortfalls']],
                         [('exam', 'Final', 2.25)])
        self.assertEqual(datetime.fromisoformat(response['shortfalls'][0]['due_date']), final.starts_at)

    def test_locked_exam_sessions_are_kept_and_count_toward_the_workload(self):
        midterm = self.exam('Midterm', '2026-11-11T09:00', 2)
        locked = StudySession.objects.create(exam=midterm, is_locked=True,
                                             starts_at=eastern('2026-11-09T12:00'), ends_at=eastern('2026-11-09T13:00'))
        self.generate()
        self.assertTrue(StudySession.objects.filter(pk=locked.pk, is_locked=True).exists())
        self.assertEqual(self.times(midterm), [('Mon 09:00', '10:00'), ('Mon 12:00', '13:00')])

    def test_completed_sessions_are_kept_and_count_toward_the_workload(self):
        essay = self.task('Essay', '2026-11-11T23:59', 3)
        done = StudySession.objects.create(assignment=essay, is_complete=True,
                                           starts_at=eastern('2026-11-09T09:00'), ends_at=eastern('2026-11-09T11:00'))
        self.generate()
        self.assertTrue(StudySession.objects.filter(pk=done.pk, is_complete=True).exists())
        self.assertEqual(self.times(essay), [('Mon 09:00', '11:00'), ('Mon 11:00', '12:00')])
        self.assertEqual(StudySession.objects.filter(assignment=essay, is_complete=False).count(), 1)

