import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.coursework.models import Assignment, Course


class ApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )

    def json_post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type='application/json')

    def json_put(self, url, body):
        return self.client.put(url, json.dumps(body), content_type='application/json')

    def json_patch(self, url, body):
        return self.client.patch(url, json.dumps(body), content_type='application/json')


class SessionApiTests(ApiTestCase):
    def test_session_sets_csrf_cookie_and_reports_auth_state(self):
        response = self.client.get(reverse('api:session'))
        self.assertFalse(response.json()['authenticated'])
        self.assertIn('csrftoken', response.cookies)
        self.client.force_login(self.user)
        response = self.client.get(reverse('api:session'))
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['user']['email'], 'student@nyu.edu')

    def test_login_signup_and_logout(self):
        response = self.json_post(reverse('api:login'), {
            'email': 'STUDENT@nyu.edu', 'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], 'student@nyu.edu')
        self.assertEqual(self.json_post(reverse('api:logout'), {}).status_code, 200)
        response = self.json_post(reverse('api:signup'), {
            'email': 'new@nyu.edu', 'password': 'strongpass456', 'password_confirm': 'strongpass456',
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email='new@nyu.edu').exists())

    def test_signup_returns_validation_errors_without_creating_user(self):
        response = self.json_post(reverse('api:signup'), {
            'email': 'not-an-email',
            'password': '12345678',
            'password_confirm': 'different',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])
        self.assertIn('password2', response.json()['errors'])
        self.assertEqual(User.objects.count(), 1)


class CourseworkApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.course = Course.objects.create(
            owner=self.user, name='Software Engineering', code='CS-GY 6063', semester='Fall 2026',
        )
        self.assignment = Assignment.objects.create(
            course=self.course,
            title='Sprint review',
            due_date=timezone.now() + timedelta(days=2),
        )

    def test_dashboard_returns_owned_data_and_metrics(self):
        response = self.client.get(reverse('api:dashboard'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['metrics']['courses'], 1)
        self.assertEqual(payload['metrics']['due_this_week'], 1)
        self.assertEqual(payload['courses'][0]['name'], 'Software Engineering')
        self.assertEqual(payload['assignments'][0]['title'], 'Sprint review')

    def test_course_crud_and_three_semester_choices(self):
        response = self.client.get(reverse('api:courses'))
        self.assertEqual(len(response.json()['semester']['choices']), 3)
        semester = response.json()['semester']['default']
        response = self.json_post(reverse('api:courses'), {
            'name': 'Independent Study', 'code': 'CS-GY 9033', 'semester': semester,
        })
        self.assertEqual(response.status_code, 201)
        course_id = response.json()['course']['id']
        response = self.json_put(reverse('api:course', args=[course_id]), {
            'name': 'Guided Study', 'code': '', 'semester': semester,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['course']['name'], 'Guided Study')

    def test_assignment_create_edit_complete_and_reopen(self):
        response = self.json_post(reverse('api:course_assignments', args=[self.course.pk]), {
            'title': 'Demo', 'due_date': '2026-11-20T17:45', 'description': 'Prepare slides.',
        })
        self.assertEqual(response.status_code, 201)
        assignment_id = response.json()['assignment']['id']
        response = self.json_put(reverse('api:assignment', args=[assignment_id]), {
            'title': 'Final demo', 'due_date': '2026-11-21T17:45', 'description': 'Prepare slides.',
        })
        self.assertEqual(response.status_code, 200)
        response = self.json_patch(reverse('api:assignment', args=[assignment_id]), {'status': 'complete'})
        self.assertEqual(response.json()['assignment']['status'], 'complete')
        response = self.json_patch(reverse('api:assignment', args=[assignment_id]), {'status': 'incomplete'})
        self.assertEqual(response.json()['assignment']['status'], 'incomplete')

    def test_ownership_and_auth_are_enforced(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='pass12345')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('api:course', args=[self.course.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('api:assignment', args=[self.assignment.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('api:dashboard')).status_code, 401)


class ReactShellTests(TestCase):
    def test_root_redirects_to_dashboard(self):
        response = self.client.get('/')

        self.assertRedirects(
            response,
            '/app/dashboard',
            fetch_redirect_response=False,
        )

    def test_spa_routes_render_the_react_shell(self):
        response = self.client.get('/app/courses/new')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=True)
        self.assertContains(response, 'frontend/app.js')

    def test_removed_template_routes_are_not_exposed(self):
        self.assertEqual(self.client.get('/accounts/login/').status_code, 404)
        self.assertEqual(self.client.get('/courses/1/').status_code, 404)
