from datetime import date, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User

from .forms import AssignmentForm, CourseForm, ExamForm
from .models import Assignment, Course, Exam


class CourseFormTests(SimpleTestCase):
    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 9, 15))
    def test_offers_previous_current_and_next_terms(self, _localdate):
        form = CourseForm()

        self.assertEqual(
            list(form.fields['semester'].choices),
            [
                ('Summer 2026', 'Summer 2026'),
                ('Fall 2026', 'Fall 2026 (current)'),
                ('Spring 2027', 'Spring 2027'),
            ],
        )
        self.assertEqual(form.initial['semester'], 'Fall 2026')

    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 1, 15))
    def test_term_window_crosses_year_boundary(self, _localdate):
        form = CourseForm()

        self.assertEqual(
            [value for value, _label in form.fields['semester'].choices],
            ['Fall 2025', 'Spring 2026', 'Summer 2026'],
        )

    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 9, 15))
    def test_accepts_varied_course_code_and_optional_code(self, _localdate):
        with_code = CourseForm({
            'name': 'Independent Study',
            'code': 'CS-GY 9033',
            'semester': 'Fall 2026',
        })
        without_code = CourseForm({
            'name': 'Product Studio',
            'code': '',
            'semester': 'Fall 2026',
        })

        self.assertTrue(with_code.is_valid(), with_code.errors)
        self.assertTrue(without_code.is_valid(), without_code.errors)


class SavedCourseFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu',
            email='student@nyu.edu',
            password='a-strong-test-password-2026',
        )

    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 9, 15))
    def test_keeps_saved_historical_semester_available_while_editing(self, _localdate):
        course = Course.objects.create(
            owner=self.user,
            name='Archived Seminar',
            semester='Spring 2024',
        )

        choices = list(CourseForm(instance=course).fields['semester'].choices)

        self.assertEqual(choices[0], ('Spring 2024', 'Spring 2024'))
        self.assertEqual(len(choices), 4)


class AssignmentFormTests(SimpleTestCase):
    def test_requires_explicit_deadline_date_and_time(self):
        missing = AssignmentForm({'title': 'Demo', 'due_date': '', 'description': ''})
        date_only = AssignmentForm({'title': 'Demo', 'due_date': '2026-11-20', 'description': ''})

        self.assertFalse(missing.is_valid())
        self.assertEqual(
            missing.errors['due_date'],
            ['A deadline date and time are required.'],
        )
        self.assertFalse(date_only.is_valid())
        self.assertEqual(
            date_only.errors['due_date'],
            ['Enter a valid deadline date and time.'],
        )

    def test_accepts_datetime_and_optional_description(self):
        form = AssignmentForm({
            'title': 'Demo',
            'due_date': '2026-11-20T17:45',
            'description': '',
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_priority_and_estimated_workload_are_optional(self):
        form = AssignmentForm({
            'title': 'Demo',
            'due_date': '2026-11-20T17:45',
            'priority': '',
            'estimated_workload': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['priority'], '')
        self.assertIsNone(form.cleaned_data['estimated_workload'])

    def test_accepts_priority_and_positive_estimated_hours(self):
        for priority in ('low', 'medium', 'high'):
            form = AssignmentForm({
                'title': 'Demo',
                'due_date': '2026-11-20T17:45',
                'priority': priority,
                'estimated_workload': '3.5',
            })
            self.assertTrue(form.is_valid(), form.errors)

        half_hour = AssignmentForm({
            'title': 'Demo',
            'due_date': '2026-11-20T17:45',
            'estimated_workload': '0.5',
        })
        self.assertTrue(half_hour.is_valid(), half_hour.errors)

    def test_rejects_unknown_priority_and_non_positive_workload(self):
        form = AssignmentForm({
            'title': 'Demo',
            'due_date': '2026-11-20T17:45',
            'priority': 'urgent',
            'estimated_workload': '0.1',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('priority', form.errors)
        self.assertIn('estimated_workload', form.errors)


class AssignmentModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu',
            email='student@nyu.edu',
            password='a-strong-test-password-2026',
        )
        self.other_user = User.objects.create_user(
            username='other@nyu.edu',
            email='other@nyu.edu',
            password='a-different-test-password-2026',
        )
        self.course = Course.objects.create(
            owner=self.user,
            name='Software Engineering',
            semester='Fall 2026',
        )
        self.other_course = Course.objects.create(
            owner=self.other_user,
            name='Databases',
            semester='Fall 2026',
        )

    def test_assignment_starts_incomplete_and_can_complete_and_reopen(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title='Sprint review',
            due_date=timezone.now() + timedelta(days=1),
        )

        self.assertFalse(assignment.is_complete)
        self.assertIsNone(assignment.completed_at)

        assignment.mark_complete()
        self.assertTrue(assignment.is_complete)
        self.assertIsNotNone(assignment.completed_at)

        assignment.reopen()
        self.assertFalse(assignment.is_complete)
        self.assertIsNone(assignment.completed_at)

    def test_overdue_only_applies_to_incomplete_past_deadlines(self):
        past = Assignment.objects.create(
            course=self.course,
            title='Past',
            due_date=timezone.now() - timedelta(hours=1),
        )
        future = Assignment.objects.create(
            course=self.course,
            title='Future',
            due_date=timezone.now() + timedelta(hours=1),
        )

        self.assertTrue(past.is_overdue)
        self.assertFalse(future.is_overdue)
        past.mark_complete()
        self.assertFalse(past.is_overdue)

    def test_owned_by_never_returns_another_users_assignments(self):
        own = Assignment.objects.create(course=self.course, title='Own')
        Assignment.objects.create(course=self.other_course, title='Other')

        self.assertEqual(list(Assignment.objects.owned_by(self.user)), [own])

    def test_outstanding_orders_deadlines_soonest_first_and_null_last(self):
        later = Assignment.objects.create(
            course=self.course,
            title='Later',
            due_date=timezone.now() + timedelta(days=2),
        )
        no_deadline = Assignment.objects.create(
            course=self.course,
            title='Legacy without deadline',
        )
        sooner = Assignment.objects.create(
            course=self.course,
            title='Sooner',
            due_date=timezone.now() + timedelta(days=1),
        )
        completed = Assignment.objects.create(
            course=self.course,
            title='Completed',
            due_date=timezone.now(),
            status=Assignment.Status.COMPLETE,
            completed_at=timezone.now(),
        )

        self.assertEqual(
            list(Assignment.objects.outstanding()),
            [sooner, later, no_deadline],
        )
        self.assertNotIn(completed, Assignment.objects.outstanding())

    def test_completed_orders_most_recent_first(self):
        earlier = Assignment.objects.create(
            course=self.course,
            title='Earlier',
            status=Assignment.Status.COMPLETE,
            completed_at=timezone.now() - timedelta(days=1),
        )
        later = Assignment.objects.create(
            course=self.course,
            title='Later',
            status=Assignment.Status.COMPLETE,
            completed_at=timezone.now(),
        )

        self.assertEqual(list(Assignment.objects.completed()), [later, earlier])


class ExamFormTests(SimpleTestCase):
    def test_requires_title_and_explicit_date_and_time(self):
        form = ExamForm({'title': '', 'starts_at': '', 'location': ''})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['title'], ['Exam title is required.'])
        self.assertEqual(form.errors['starts_at'], ['An exam date and time are required.'])

        for value in ('2026-12-10', 'not-a-date', '2026-13-40T09:00'):
            form = ExamForm({'title': 'Final', 'starts_at': value})
            self.assertFalse(form.is_valid(), value)
            self.assertEqual(form.errors['starts_at'], ['Enter a valid exam date and time.'])

    def test_location_is_optional(self):
        self.assertTrue(ExamForm({'title': 'Midterm', 'starts_at': '2026-11-05T14:00'}).is_valid())
        self.assertTrue(ExamForm({'title': 'Midterm', 'starts_at': '2026-11-05T14:00', 'location': 'Jacobs 474'}).is_valid())

    def test_priority_and_estimated_workload_are_optional(self):
        form = ExamForm({
            'title': 'Midterm',
            'starts_at': '2026-11-05T14:00',
            'priority': '',
            'estimated_workload': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['estimated_workload'])

    def test_accepts_priority_and_estimated_hours(self):
        form = ExamForm({
            'title': 'Midterm',
            'starts_at': '2026-11-05T14:00',
            'priority': 'high',
            'estimated_workload': '8.5',
        })

        self.assertTrue(form.is_valid(), form.errors)


class ExamModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='testpass123')
        self.course = Course.objects.create(owner=self.user, name='Algorithms', semester='Fall 2026')

    def test_upcoming_hides_past_exams_and_orders_soonest_first(self):
        now = timezone.now()
        Exam.objects.create(course=self.course, title='Quiz 1', starts_at=now - timedelta(days=1))
        later = Exam.objects.create(course=self.course, title='Final', starts_at=now + timedelta(days=30))
        sooner = Exam.objects.create(course=self.course, title='Midterm', starts_at=now + timedelta(days=5))

        self.assertEqual(list(Exam.objects.upcoming()), [sooner, later])

    def test_owned_by_never_returns_another_users_exams(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='testpass123')
        other_course = Course.objects.create(owner=other, name='Other', semester='Fall 2026')
        mine = Exam.objects.create(course=self.course, title='Midterm', starts_at=timezone.now())
        Exam.objects.create(course=other_course, title='Theirs', starts_at=timezone.now())

        self.assertEqual(list(Exam.objects.owned_by(self.user)), [mine])
