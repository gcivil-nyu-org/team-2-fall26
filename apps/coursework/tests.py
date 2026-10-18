from datetime import date, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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
            'due_date': date.today() + timedelta(days=3),
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
