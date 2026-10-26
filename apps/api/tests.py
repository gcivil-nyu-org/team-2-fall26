import json
from datetime import timedelta

from django.test import TestCase, override_settings
from django.templatetags.static import static
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

    def test_delete_removes_assignment_and_its_details_link(self):
        response = self.client.delete(reverse('api:assignment', args=[self.assignment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertEqual(self.client.get(reverse('api:assignment', args=[self.assignment.pk])).status_code, 404)
        self.assertEqual(self.client.delete(reverse('api:assignment', args=[self.assignment.pk])).status_code, 404)

    def test_deleted_assignment_disappears_from_all_coursework_views(self):
        self.assignment.mark_complete()
        self.client.delete(reverse('api:assignment', args=[self.assignment.pk]))
        course = self.client.get(reverse('api:course', args=[self.course.pk])).json()['course']
        self.assertEqual(course['assignments'], [])
        self.assertEqual(course['assignment_count'], 0)
        self.assertEqual(self.client.get(reverse('api:dashboard')).json()['assignments'], [])
        self.assertEqual(self.client.get(reverse('api:assignments')).json()['assignments'], [])
        completed = self.client.get(reverse('api:assignments'), {'status': 'complete'}).json()
        self.assertEqual(completed['assignments'], [])

    def test_delete_preserves_course_and_other_assignments(self):
        sibling = Assignment.objects.create(course=self.course, title='Retro notes')
        self.client.delete(reverse('api:assignment', args=[self.assignment.pk]))
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())
        course = self.client.get(reverse('api:course', args=[self.course.pk])).json()['course']
        self.assertEqual([item['id'] for item in course['assignments']], [sibling.pk])

    def test_delete_is_limited_to_the_owner(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='pass12345')
        self.client.force_login(other)
        self.assertEqual(self.client.delete(reverse('api:assignment', args=[self.assignment.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.delete(reverse('api:assignment', args=[self.assignment.pk])).status_code, 401)
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_delete_course_removes_it_and_its_assignments(self):
        second = Assignment.objects.create(course=self.course, title='Retro notes')
        response = self.client.delete(reverse('api:course', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())
        self.assertFalse(Assignment.objects.filter(pk__in=[self.assignment.pk, second.pk]).exists())
        self.assertEqual(self.client.get(reverse('api:course', args=[self.course.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('api:assignment', args=[second.pk])).status_code, 404)

    def test_deleted_course_disappears_from_course_list_and_outstanding_work(self):
        self.client.delete(reverse('api:course', args=[self.course.pk]))
        self.assertEqual(self.client.get(reverse('api:courses')).json()['courses'], [])
        dashboard = self.client.get(reverse('api:dashboard')).json()
        self.assertEqual(dashboard['courses'], [])
        self.assertEqual(dashboard['assignments'], [])
        self.assertEqual(dashboard['metrics']['courses'], 0)

    def test_delete_course_preserves_other_courses(self):
        other_course = Course.objects.create(owner=self.user, name='Algorithms', semester='Fall 2026')
        kept = Assignment.objects.create(course=other_course, title='Problem set 1')
        self.client.delete(reverse('api:course', args=[self.course.pk]))
        courses = self.client.get(reverse('api:courses')).json()['courses']
        self.assertEqual([item['id'] for item in courses], [other_course.pk])
        self.assertTrue(Assignment.objects.filter(pk=kept.pk).exists())

    def test_delete_course_is_limited_to_the_owner(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='pass12345')
        self.client.force_login(other)
        self.assertEqual(self.client.delete(reverse('api:course', args=[self.course.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.delete(reverse('api:course', args=[self.course.pk])).status_code, 401)
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())

    def test_description_edit_preserves_utc_deadline_and_completion_state(self):
        response = self.json_post(reverse('api:course_assignments', args=[self.course.pk]), {
            'title': 'Deadline regression', 'due_date': '2026-11-20T17:45', 'description': 'Original',
        })
        self.assertEqual(response.status_code, 201)
        assignment_id = response.json()['assignment']['id']
        url = reverse('api:assignment', args=[assignment_id])
        self.json_patch(url, {'status': 'complete'})
        before = self.client.get(url).json()['assignment']
        response = self.json_put(url, {
            'title': before['title'], 'description': 'Updated description',
            'due_date': '2026-11-20T17:45',
        })
        self.assertEqual(response.status_code, 200)
        after = self.client.get(url).json()['assignment']
        self.assertEqual(after['due_date'], '2026-11-20T17:45:00+00:00')
        self.assertEqual(after['due_date'], before['due_date'])
        self.assertEqual(after['description'], 'Updated description')
        self.assertEqual(after['status'], before['status'])
        self.assertEqual(after['completed_at'], before['completed_at'])


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
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
        self.assertContains(response, static('frontend/app.js'))

    def test_removed_template_routes_are_not_exposed(self):
        self.assertEqual(self.client.get('/accounts/login/').status_code, 404)
        self.assertEqual(self.client.get('/courses/1/').status_code, 404)
