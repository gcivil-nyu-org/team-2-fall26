from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from .models import Assignment, Course
from .forms import CourseForm


class CourseFormTests(SimpleTestCase):
    def test_semester_defaults_follow_calendar_boundaries(self):
        cases = [
            (date(2026, 1, 1), 'Spring 2026'),
            (date(2026, 5, 31), 'Spring 2026'),
            (date(2026, 6, 1), 'Summer 2026'),
            (date(2026, 8, 31), 'Summer 2026'),
            (date(2026, 9, 1), 'Fall 2026'),
            (date(2026, 12, 31), 'Fall 2026'),
            (date(2027, 1, 1), 'Spring 2027'),
        ]
        for today, expected in cases:
            with self.subTest(today=today), patch('apps.coursework.forms.timezone.localdate', return_value=today):
                self.assertEqual(CourseForm()['semester'].value(), expected)

    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 9, 15))
    def test_can_choose_previous_semester_and_varied_course_code(self, mock_today):
        form = CourseForm(data={
            'name': 'Independent Study', 'code': 'CS-GY 9033', 'semester': 'Summer 2026',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).semester, 'Summer 2026')
        self.assertEqual(form['semester'].value(), 'Summer 2026')
        self.assertIn(('Spring 2027', 'Spring 2027'), form.fields['semester'].choices)

    @patch('apps.coursework.forms.timezone.localdate', return_value=date(2026, 10, 18))
    def test_validation_keeps_selected_semester_and_does_not_fill_missing_input(self, mock_today):
        form = CourseForm(data={'name': '', 'semester': 'Summer 2026'})
        self.assertFalse(form.is_valid())
        self.assertEqual(form['semester'].value(), 'Summer 2026')
        missing = CourseForm(data={'name': 'Independent Study', 'semester': ''})
        self.assertFalse(missing.is_valid())
        self.assertEqual(missing.errors['semester'], ['Semester is required.'])

    def test_only_adjacent_semesters_are_offered_across_year_boundaries(self):
        cases = [
            (date(2026, 1, 1), ['Fall 2025', 'Spring 2026', 'Summer 2026']),
            (date(2026, 7, 1), ['Spring 2026', 'Summer 2026', 'Fall 2026']),
            (date(2026, 10, 18), ['Summer 2026', 'Fall 2026', 'Spring 2027']),
        ]
        for today, expected in cases:
            with self.subTest(today=today), patch('apps.coursework.forms.timezone.localdate', return_value=today):
                form = CourseForm()
                self.assertEqual([value for value, label in form.fields['semester'].choices], expected)
                invalid = CourseForm(data={'name': 'Independent Study', 'semester': 'Fall 2024'})
                self.assertFalse(invalid.is_valid())
                self.assertIn('semester', invalid.errors)


class CourseCreateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )
        self.client.login(username='student@nyu.edu', password='testpass123')

    def test_create_course_with_name_code_and_semester(self):
        response = self.client.post(reverse('coursework:course_add'), {
            'name': 'Software Engineering',
            'code': 'CSCI-UA 101',
            'semester': 'Fall 2026',
        })
        self.assertEqual(Course.objects.count(), 1)
        course = Course.objects.get()
        self.assertEqual(course.name, 'Software Engineering')
        self.assertEqual(course.code, 'CSCI-UA 101')
        self.assertEqual(course.semester, 'Fall 2026')
        self.assertEqual(course.owner, self.user)
        self.assertRedirects(response, reverse('coursework:course_detail', args=[course.pk]))

    def test_course_code_is_optional(self):
        self.client.post(reverse('coursework:course_add'), {
            'name': 'Independent Study',
            'code': '',
            'semester': 'Fall 2026',
        })
        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Course.objects.get().code, '')

    def test_missing_name_is_rejected(self):
        response = self.client.post(reverse('coursework:course_add'), {
            'name': '',
            'code': 'CSCI-UA 101',
            'semester': 'Fall 2026',
        })
        self.assertEqual(Course.objects.count(), 0)
        self.assertContains(response, 'Course name is required.')

    def test_missing_semester_is_rejected(self):
        response = self.client.post(reverse('coursework:course_add'), {
            'name': 'Software Engineering',
            'code': 'CSCI-UA 101',
            'semester': '',
        })
        self.assertEqual(Course.objects.count(), 0)
        self.assertContains(response, 'Semester is required.')

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse('coursework:course_add'))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('coursework:course_add')}",
        )


class CourseListAndPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )
        self.client.login(username='student@nyu.edu', password='testpass123')

    def test_saved_course_appears_on_dashboard_after_refresh(self):
        self.client.post(reverse('coursework:course_add'), {
            'name': 'Software Engineering',
            'code': 'CSCI-UA 101',
            'semester': 'Fall 2026',
        })
        first = self.client.get(reverse('accounts:dashboard'))
        self.assertContains(first, 'Software Engineering')
        second = self.client.get(reverse('accounts:dashboard'))
        self.assertContains(second, 'Software Engineering')
        self.assertContains(second, 'CSCI-UA 101')
        self.assertContains(second, 'Fall 2026')
        self.assertEqual(second.context['course_count'], 1)


class CourseDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )
        self.client.login(username='student@nyu.edu', password='testpass123')
        self.course = Course.objects.create(
            owner=self.user, name='Software Engineering', code='CSCI-UA 101', semester='Fall 2026',
        )

    def test_new_course_shows_empty_assignments_and_add_option(self):
        response = self.client.get(reverse('coursework:course_detail', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No assignments yet')
        self.assertContains(response, 'Add assignment')
        add_url = reverse('coursework:assignment_add', args=[self.course.pk])
        self.assertContains(response, add_url)

    def test_can_add_assignment_to_course(self):
        response = self.client.post(reverse('coursework:assignment_add', args=[self.course.pk]), {
            'title': 'Homework 1',
            'due_date': '2026-10-24T14:30',
        })
        self.assertRedirects(response, reverse('coursework:course_detail', args=[self.course.pk]))
        self.assertEqual(self.course.assignments.count(), 1)
        detail = self.client.get(reverse('coursework:course_detail', args=[self.course.pk]))
        self.assertContains(detail, 'Homework 1')


class CourseOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@nyu.edu', email='owner@nyu.edu', password='testpass123',
        )
        self.other = User.objects.create_user(
            username='other@nyu.edu', email='other@nyu.edu', password='testpass123',
        )
        self.course = Course.objects.create(
            owner=self.owner, name='Owner Course', code='CSCI-UA 2', semester='Fall 2026',
        )

    def test_other_student_cannot_view_course(self):
        self.client.login(username='other@nyu.edu', password='testpass123')
        response = self.client.get(reverse('coursework:course_detail', args=[self.course.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_student_cannot_add_assignment_to_course(self):
        self.client.login(username='other@nyu.edu', password='testpass123')
        response = self.client.post(reverse('coursework:assignment_add', args=[self.course.pk]), {
            'title': 'Not mine',
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Assignment.objects.count(), 0)

    def test_other_student_does_not_see_course_on_dashboard(self):
        self.client.login(username='other@nyu.edu', password='testpass123')
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertNotContains(response, 'Owner Course')
        self.assertContains(response, 'No courses yet')


class AssignmentStatusTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )
        self.client.login(username='student@nyu.edu', password='testpass123')
        self.course = Course.objects.create(
            owner=self.user, name='Software Engineering', code='CSCI-UA 101', semester='Fall 2026',
        )
        self.today = timezone.now().replace(second=0, microsecond=0)

    def make_assignment(self, title, days_from_today=3, **kwargs):
        due_date = None if days_from_today is None else self.today + timedelta(days=days_from_today)
        return Assignment.objects.create(course=self.course, title=title, due_date=due_date, **kwargs)

    def complete(self, assignment, **data):
        return self.client.post(reverse('coursework:assignment_complete', args=[assignment.pk]), data)

    def reopen(self, assignment, **data):
        return self.client.post(reverse('coursework:assignment_reopen', args=[assignment.pk]), data)

    def outstanding_titles(self):
        response = self.client.get(reverse('accounts:dashboard'))
        return [a.title for a in response.context['outstanding_assignments']]

    def completed_titles(self):
        response = self.client.get(reverse('coursework:completed_assignments'))
        return [a.title for a in response.context['assignments']]


class AssignmentCompletionTests(AssignmentStatusTestCase):
    def test_new_assignment_starts_incomplete(self):
        self.client.post(reverse('coursework:assignment_add', args=[self.course.pk]), {
            'title': 'Homework 1', 'due_date': (self.today + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
        })
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.status, Assignment.Status.INCOMPLETE)
        self.assertIsNone(assignment.completed_at)

    def test_mark_complete_changes_status(self):
        assignment = self.make_assignment('Homework 1')
        response = self.complete(assignment)
        self.assertRedirects(response, reverse('coursework:course_detail', args=[self.course.pk]))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, Assignment.Status.COMPLETE)
        self.assertIsNotNone(assignment.completed_at)

    def test_mark_complete_returns_to_safe_next_url(self):
        assignment = self.make_assignment('Homework 1')
        response = self.complete(assignment, next=reverse('accounts:dashboard'))
        self.assertRedirects(response, reverse('accounts:dashboard'))

    def test_mark_complete_ignores_external_next_url(self):
        assignment = self.make_assignment('Homework 1')
        response = self.complete(assignment, next='https://evil.example.com/')
        self.assertRedirects(response, reverse('coursework:course_detail', args=[self.course.pk]))

    def test_get_request_does_not_change_status(self):
        assignment = self.make_assignment('Homework 1')
        response = self.client.get(reverse('coursework:assignment_complete', args=[assignment.pk]))
        self.assertEqual(response.status_code, 405)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, Assignment.Status.INCOMPLETE)

    def test_course_detail_shows_complete_and_reopen_actions(self):
        open_assignment = self.make_assignment('Homework 1')
        done_assignment = self.make_assignment('Homework 2', status=Assignment.Status.COMPLETE)
        response = self.client.get(reverse('coursework:course_detail', args=[self.course.pk]))
        self.assertContains(response, reverse('coursework:assignment_complete', args=[open_assignment.pk]))
        self.assertContains(response, reverse('coursework:assignment_reopen', args=[done_assignment.pk]))


class AssignmentReopenTests(AssignmentStatusTestCase):
    def test_reopen_changes_status_back_to_incomplete(self):
        assignment = self.make_assignment('Homework 1')
        self.complete(assignment)
        response = self.reopen(assignment)
        self.assertRedirects(response, reverse('coursework:course_detail', args=[self.course.pk]))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, Assignment.Status.INCOMPLETE)
        self.assertIsNone(assignment.completed_at)

    def test_reopened_assignment_returns_to_outstanding_view(self):
        assignment = self.make_assignment('Homework 1')
        self.complete(assignment)
        self.reopen(assignment)
        self.assertIn('Homework 1', self.outstanding_titles())
        self.assertNotIn('Homework 1', self.completed_titles())

    def test_reopened_past_due_assignment_is_overdue_and_ordered_by_deadline(self):
        self.make_assignment('Later', days_from_today=5)
        self.make_assignment('Undated', days_from_today=None)
        late = self.make_assignment('Late essay', days_from_today=-2)
        self.complete(late)
        self.reopen(late)

        self.assertEqual(self.outstanding_titles(), ['Late essay', 'Later', 'Undated'])
        late.refresh_from_db()
        self.assertTrue(late.is_overdue)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertContains(response, 'Overdue</span>')
        self.assertEqual(response.context['overdue_count'], 1)


class AssignmentListVisibilityTests(AssignmentStatusTestCase):
    def test_completed_assignment_leaves_outstanding_view(self):
        assignment = self.make_assignment('Homework 1')
        self.make_assignment('Homework 2')
        self.complete(assignment)
        self.assertEqual(self.outstanding_titles(), ['Homework 2'])

    def test_completed_assignment_appears_in_completed_view(self):
        assignment = self.make_assignment('Homework 1')
        self.make_assignment('Homework 2')
        self.complete(assignment)
        self.assertEqual(self.completed_titles(), ['Homework 1'])
        response = self.client.get(reverse('coursework:completed_assignments'))
        self.assertContains(response, reverse('coursework:assignment_reopen', args=[assignment.pk]))

    def test_dashboard_links_to_completed_view(self):
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertContains(response, reverse('coursework:completed_assignments'))

    def test_overdue_incomplete_assignment_stays_outstanding(self):
        self.make_assignment('Late essay', days_from_today=-1)
        self.assertEqual(self.outstanding_titles(), ['Late essay'])

    def test_dashboard_counts_exclude_completed_assignments(self):
        due_soon = self.make_assignment('Due soon', days_from_today=2)
        overdue = self.make_assignment('Overdue', days_from_today=-2)
        self.make_assignment('Still open', days_from_today=1)
        self.complete(due_soon)
        self.complete(overdue)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.context['due_this_week_count'], 1)
        self.assertEqual(response.context['overdue_count'], 0)

    def test_completed_view_empty_state(self):
        response = self.client.get(reverse('coursework:completed_assignments'))
        self.assertContains(response, 'Nothing completed yet')


class AssignmentStatusPersistenceTests(AssignmentStatusTestCase):
    def test_completion_persists_after_refresh(self):
        assignment = self.make_assignment('Homework 1')
        self.complete(assignment)
        for _ in range(2):
            self.assertNotIn('Homework 1', self.outstanding_titles())
            self.assertIn('Homework 1', self.completed_titles())
        self.assertEqual(Assignment.objects.get(pk=assignment.pk).status, Assignment.Status.COMPLETE)

    def test_reopen_persists_after_refresh(self):
        assignment = self.make_assignment('Homework 1')
        self.complete(assignment)
        self.reopen(assignment)
        for _ in range(2):
            self.assertIn('Homework 1', self.outstanding_titles())
            self.assertNotIn('Homework 1', self.completed_titles())
        self.assertEqual(Assignment.objects.get(pk=assignment.pk).status, Assignment.Status.INCOMPLETE)


class AssignmentStatusIsolationTests(AssignmentStatusTestCase):
    def setUp(self):
        super().setUp()
        self.assignment = self.make_assignment('Owner homework')
        self.other = User.objects.create_user(
            username='other@nyu.edu', email='other@nyu.edu', password='testpass123',
        )

    def login_as_other(self):
        self.client.logout()
        self.client.login(username='other@nyu.edu', password='testpass123')

    def test_other_student_cannot_complete_assignment(self):
        self.login_as_other()
        response = self.complete(self.assignment)
        self.assertEqual(response.status_code, 404)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, Assignment.Status.INCOMPLETE)

    def test_other_student_cannot_reopen_assignment(self):
        self.assignment.mark_complete()
        self.login_as_other()
        response = self.reopen(self.assignment)
        self.assertEqual(response.status_code, 404)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, Assignment.Status.COMPLETE)

    def test_other_student_does_not_see_completed_assignment(self):
        self.assignment.mark_complete()
        self.login_as_other()
        self.assertEqual(self.completed_titles(), [])
        self.assertNotContains(
            self.client.get(reverse('coursework:completed_assignments')), 'Owner homework',
        )

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        complete_url = reverse('coursework:assignment_complete', args=[self.assignment.pk])
        response = self.client.post(complete_url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={complete_url}")
        completed_url = reverse('coursework:completed_assignments')
        response = self.client.get(completed_url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={completed_url}")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, Assignment.Status.INCOMPLETE)


class AssignmentDeadlineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='deadline@nyu.edu', email='deadline@nyu.edu', password='testpass123')
        self.course = Course.objects.create(owner=self.user, name='Deadlines', semester='Fall 2026')
        self.client.force_login(self.user)
        self.url = reverse('coursework:assignment_add', args=[self.course.pk])

    def test_creation_persists_deadline_description_and_initial_status(self):
        response = self.client.post(self.url, {
            'title': 'Project', 'due_date': '2026-11-02T14:30', 'description': 'Submit report',
            'status': 'complete',
        })
        self.assertRedirects(response, reverse('coursework:course_detail', args=[self.course.pk]))
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.status, Assignment.Status.INCOMPLETE)
        self.assertEqual(assignment.description, 'Submit report')
        self.assertEqual(assignment.due_date.isoformat(), '2026-11-02T14:30:00+00:00')
        for _ in range(2):
            detail = self.client.get(reverse('coursework:course_detail', args=[self.course.pk]))
            self.assertContains(detail, 'Project')
            self.assertContains(detail, 'Submit report')
            self.assertContains(detail, 'Incomplete')
            self.assertContains(detail, '2:30 p.m. UTC')

    def test_required_and_invalid_input_prevents_saving(self):
        for title, deadline, error in [
            ('', '2026-11-02T14:30', 'This field is required.'),
            ('Project', '', 'A deadline date and time are required.'),
            ('Project', 'invalid', 'Enter a valid deadline date and time.'),
            ('Project', '2026-02-30T12:00', 'Enter a valid deadline date and time.'),
            ('Project', '2026-11-02', 'Enter a valid deadline date and time.'),
        ]:
            with self.subTest(title=title, deadline=deadline):
                response = self.client.post(self.url, {'title': title, 'due_date': deadline})
                self.assertContains(response, error)
                self.assertFalse(Assignment.objects.exists())

    def test_past_deadline_without_description_is_allowed_and_visible(self):
        self.client.post(self.url, {'title': 'Overdue report', 'due_date': '2020-01-01T09:00'})
        self.assertEqual(Assignment.objects.get().description, '')
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertContains(response, 'Overdue report')
        self.assertEqual(response.context['overdue_count'], 1)

    def test_timezone_is_indicated_on_form(self):
        self.assertContains(self.client.get(self.url), 'Time zone: UTC.')

    def test_anonymous_creation_is_rejected(self):
        self.client.logout()
        response = self.client.post(self.url, {'title': 'Hidden', 'due_date': '2026-11-02T14:30'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Assignment.objects.exists())

    def test_other_account_cannot_read_or_create_assignments(self):
        Assignment.objects.create(course=self.course, title='Private project', due_date='2026-11-02T14:30:00Z')
        other = User.objects.create_user(username='outsider', email='outsider@nyu.edu')
        self.client.force_login(other)
        for method in [self.client.get, self.client.post]:
            response = method(self.url, {'title': 'Intrusion', 'due_date': '2026-11-02T14:30'})
            self.assertEqual(response.status_code, 404)
        self.assertEqual(Assignment.objects.count(), 1)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertNotContains(response, 'Private project')
        self.assertEqual(response.context['overdue_count'], 0)

    def test_deadline_time_controls_overdue_status_on_same_day(self):
        now = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        earlier = Assignment.objects.create(course=self.course, title='Earlier today', due_date=now - timedelta(hours=1))
        later = Assignment.objects.create(course=self.course, title='Later today', due_date=now + timedelta(hours=1))
        with patch('apps.coursework.models.timezone.now', return_value=now):
            self.assertTrue(earlier.is_overdue)
            self.assertFalse(later.is_overdue)
            self.assertEqual(list(Assignment.objects.overdue()), [earlier])
            response = self.client.get(reverse('accounts:dashboard'))
            self.assertEqual(response.context['overdue_count'], 1)
            self.assertEqual(response.context['due_this_week_count'], 1)


class AssignmentEditTests(TestCase):
    """#15: editing an assignment's title, description and deadline."""

    def setUp(self):
        self.user = User.objects.create_user(username='editor@nyu.edu', email='editor@nyu.edu', password='testpass123')
        self.course = Course.objects.create(owner=self.user, name='Software Engineering', semester='Fall 2026')
        self.client.force_login(self.user)
        self.assignment = Assignment.objects.create(
            course=self.course, title='Sprint report', description='Draft outline',
            due_date=timezone.now().replace(second=0, microsecond=0) + timedelta(days=5),
        )
        self.url = reverse('coursework:assignment_edit', args=[self.assignment.pk])
        self.detail_url = reverse('coursework:course_detail', args=[self.course.pk])
        self.dashboard_url = reverse('accounts:dashboard')

    def edit(self, **overrides):
        data = {'title': 'Final sprint report', 'due_date': '2026-11-20T17:45', 'description': 'Include retro notes'}
        data.update(overrides)
        return self.client.post(self.url, data)

    def deadline_from_now(self, **delta):
        return (timezone.now() + timedelta(**delta)).strftime('%Y-%m-%dT%H:%M')

    def outstanding_titles(self):
        response = self.client.get(self.dashboard_url)
        return [a.title for a in response.context['outstanding_assignments']]

    def test_form_shows_current_information(self):
        self.assignment.due_date = datetime(2026, 11, 2, 14, 30, tzinfo=dt_timezone.utc)
        self.assignment.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit assignment')
        self.assertContains(response, 'value="Sprint report"')
        self.assertContains(response, 'value="2026-11-02T14:30"')
        self.assertContains(response, 'Draft outline</textarea>')
        self.assertContains(response, 'Time zone: UTC.')

    def test_saves_title_description_and_deadline(self):
        response = self.edit()
        self.assertRedirects(response, self.detail_url)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Final sprint report')
        self.assertEqual(self.assignment.description, 'Include retro notes')
        self.assertEqual(self.assignment.due_date.isoformat(), '2026-11-20T17:45:00+00:00')
        self.assertEqual(Assignment.objects.count(), 1)

    def test_description_can_be_cleared(self):
        self.edit(description='')
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.description, '')

    def test_saved_changes_appear_in_details_and_list_after_refresh(self):
        self.edit()
        for _ in range(2):
            detail = self.client.get(self.detail_url)
            self.assertContains(detail, 'Final sprint report')
            self.assertContains(detail, 'Include retro notes')
            self.assertContains(detail, 'Nov 20, 2026, 5:45 p.m. UTC')
            self.assertNotContains(detail, 'Sprint report</div>')
            dashboard = self.client.get(self.dashboard_url)
            self.assertContains(dashboard, 'Final sprint report')
            self.assertContains(dashboard, 'Nov 20, 2026, 5:45 p.m. UTC')

    def test_same_validation_rules_as_creation(self):
        for title, deadline, error in [
            ('', '2026-11-02T14:30', 'This field is required.'),
            ('Project', '', 'A deadline date and time are required.'),
            ('Project', 'invalid', 'Enter a valid deadline date and time.'),
            ('Project', '2026-02-30T12:00', 'Enter a valid deadline date and time.'),
            ('Project', '2026-11-02', 'Enter a valid deadline date and time.'),
        ]:
            with self.subTest(title=title, deadline=deadline):
                response = self.edit(title=title, due_date=deadline)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                self.assignment.refresh_from_db()
                self.assertEqual(self.assignment.title, 'Sprint report')
                self.assertEqual(self.assignment.description, 'Draft outline')

    def test_assignment_without_deadline_must_get_one_when_edited(self):
        legacy = Assignment.objects.create(course=self.course, title='Old task', due_date=None)
        url = reverse('coursework:assignment_edit', args=[legacy.pk])
        response = self.client.post(url, {'title': 'Old task', 'due_date': ''})
        self.assertContains(response, 'A deadline date and time are required.')
        legacy.refresh_from_db()
        self.assertIsNone(legacy.due_date)

    def test_moving_deadline_earlier_reorders_outstanding_view(self):
        Assignment.objects.create(course=self.course, title='Midterm prep', due_date=timezone.now() + timedelta(days=2))
        self.assertEqual(self.outstanding_titles(), ['Midterm prep', 'Sprint report'])
        self.edit(title='Sprint report', due_date=self.deadline_from_now(days=1))
        self.assertEqual(self.outstanding_titles(), ['Sprint report', 'Midterm prep'])

    def test_moving_deadline_into_past_marks_overdue_and_back_clears_it(self):
        self.edit(title='Sprint report', due_date=self.deadline_from_now(days=-1))
        dashboard = self.client.get(self.dashboard_url)
        self.assertEqual(dashboard.context['overdue_count'], 1)
        self.assertContains(dashboard, 'class="overdue-badge"')
        self.assertContains(self.client.get(self.detail_url), 'class="overdue-badge"')

        self.edit(title='Sprint report', due_date=self.deadline_from_now(days=3))
        dashboard = self.client.get(self.dashboard_url)
        self.assertEqual(dashboard.context['overdue_count'], 0)
        self.assertNotContains(dashboard, 'class="overdue-badge"')
        self.assertNotContains(self.client.get(self.detail_url), 'class="overdue-badge"')
        self.assertEqual(dashboard.context['due_this_week_count'], 1)

    def test_editing_keeps_completion_status(self):
        self.assignment.mark_complete()
        completed_at = self.assignment.completed_at
        self.edit(status='incomplete')
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Final sprint report')
        self.assertEqual(self.assignment.status, Assignment.Status.COMPLETE)
        self.assertEqual(self.assignment.completed_at, completed_at)

    def test_cancel_returns_without_changing_anything(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'href="{self.detail_url}" class="btn btn-outline-secondary">Cancel')
        self.client.get(self.detail_url)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Sprint report')
        self.assertEqual(self.assignment.description, 'Draft outline')

    def test_edit_from_dashboard_returns_to_dashboard(self):
        response = self.client.get(f'{self.url}?next={self.dashboard_url}')
        self.assertContains(response, f'href="{self.dashboard_url}" class="btn btn-outline-secondary">Cancel')
        self.assertContains(response, f'name="next" value="{self.dashboard_url}"')
        response = self.client.post(self.url, {
            'title': 'Final sprint report', 'due_date': '2026-11-20T17:45', 'next': self.dashboard_url,
        })
        self.assertRedirects(response, self.dashboard_url)

    def test_external_next_url_is_ignored(self):
        response = self.client.get(f'{self.url}?next=https://evil.example.com/')
        self.assertNotContains(response, 'evil.example.com')
        response = self.edit(next='https://evil.example.com/')
        self.assertRedirects(response, self.detail_url)

    def test_course_detail_and_dashboard_link_to_edit(self):
        self.assertContains(self.client.get(self.detail_url), f'href="{self.url}"')
        self.assertContains(self.client.get(self.dashboard_url), f'href="{self.url}?next=')

    def test_other_student_cannot_view_or_edit(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='testpass123')
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.edit().status_code, 404)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Sprint report')

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.edit()
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Sprint report')
