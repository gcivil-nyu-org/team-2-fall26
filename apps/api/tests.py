import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.coursework.models import Assignment, Course, Exam


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

    def test_signup_rejects_non_nyu_email(self):
        response = self.json_post(reverse('api:signup'), {
            'email': 'student@gmail.com', 'password': 'strongpass456', 'password_confirm': 'strongpass456',
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['errors']['email'],
            ['Please sign up with your NYU email address (@nyu.edu).'],
        )
        self.assertFalse(User.objects.filter(email='student@gmail.com').exists())

    def test_signup_accepts_nyu_school_subdomain_email(self):
        response = self.json_post(reverse('api:signup'), {
            'email': 'new@stern.nyu.edu', 'password': 'strongpass456', 'password_confirm': 'strongpass456',
        })

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email='new@stern.nyu.edu').exists())


class PasswordResetApiTests(ApiTestCase):
    def _reset_link(self):
        self.json_post(reverse('api:password_reset_request'), {'email': self.user.email})
        body = mail.outbox[-1].body
        path = body.split('/app/reset-password/')[1].split('\n')[0].strip()
        uid, token = path.split('/')
        return uid, token

    def test_request_sends_email_with_a_working_link_for_an_existing_account(self):
        response = self.json_post(reverse('api:password_reset_request'), {'email': 'STUDENT@nyu.edu'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)
        self.assertIn('/app/reset-password/', mail.outbox[0].body)

    def test_request_does_not_reveal_whether_an_account_exists(self):
        response = self.json_post(reverse('api:password_reset_request'), {'email': 'nobody@nyu.edu'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_changes_the_password(self):
        uid, token = self._reset_link()

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass-456'))

    def test_confirm_rejects_a_bad_token(self):
        uid, _ = self._reset_link()

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': 'not-a-real-token', 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('testpass123'))

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_confirm_rejects_an_expired_token(self):
        uid, token = self._reset_link()

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('testpass123'))

    def test_can_log_in_with_the_new_password_after_reset(self):
        uid, token = self._reset_link()
        self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        response = self.json_post(reverse('api:login'), {
            'email': self.user.email, 'password': 'brand-new-pass-456',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], self.user.email)

    def test_a_broken_mail_server_does_not_fail_the_request(self):
        with mock.patch('apps.api.views.send_mail', side_effect=OSError('smtp unreachable')):
            response = self.json_post(reverse('api:password_reset_request'), {'email': self.user.email})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    def test_confirm_rejects_an_unknown_account(self):
        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': 'not-a-real-uid', 'token': 'not-a-real-token', 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        self.assertEqual(response.status_code, 400)

    def test_confirm_rejects_mismatched_passwords(self):
        uid, token = self._reset_link()

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'brand-new-pass-456', 'password_confirm': 'does-not-match',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('password_confirm', response.json()['errors'])

    def test_confirm_enforces_password_validators(self):
        uid, token = self._reset_link()

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': '12345678', 'password_confirm': '12345678',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json()['errors'])

    def test_a_used_token_cannot_be_reused(self):
        uid, token = self._reset_link()
        self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'brand-new-pass-456', 'password_confirm': 'brand-new-pass-456',
        })

        response = self.json_post(reverse('api:password_reset_confirm'), {
            'uid': uid, 'token': token, 'password': 'another-pass-789', 'password_confirm': 'another-pass-789',
        })

        self.assertEqual(response.status_code, 400)


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

    def test_add_exam_to_owned_course(self):
        response = self.json_post(reverse('api:course_exams', args=[self.course.pk]), {
            'title': 'Midterm', 'starts_at': '2026-11-05T14:00', 'location': 'Jacobs 474',
        })
        self.assertEqual(response.status_code, 201)
        exam = response.json()['exam']
        self.assertEqual(exam['kind'], 'exam')
        self.assertEqual(exam['location'], 'Jacobs 474')
        self.assertEqual(exam['course']['id'], self.course.pk)
        self.assertEqual(Exam.objects.get(pk=exam['id']).course, self.course)
        self.assertEqual(Assignment.objects.count(), 1)

        course = self.client.get(reverse('api:course', args=[self.course.pk])).json()['course']
        self.assertEqual([item['title'] for item in course['exams']], ['Midterm'])
        self.assertEqual([item['title'] for item in course['assignments']], ['Sprint review'])

    def test_add_exam_rejects_missing_or_invalid_fields(self):
        url = reverse('api:course_exams', args=[self.course.pk])
        response = self.json_post(url, {'title': '', 'starts_at': '', 'location': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['errors']['title'], ['Exam title is required.'])
        self.assertEqual(response.json()['errors']['starts_at'], ['An exam date and time are required.'])
        response = self.json_post(url, {'title': 'Final', 'starts_at': '2026-12-10'})
        self.assertEqual(response.json()['errors']['starts_at'], ['Enter a valid exam date and time.'])
        self.assertFalse(Exam.objects.exists())

    def test_exams_join_outstanding_work_in_deadline_order(self):
        now = timezone.now()
        Assignment.objects.create(course=self.course, title='Late essay', due_date=now - timedelta(days=1))
        Assignment.objects.create(course=self.course, title='Someday reading')
        Exam.objects.create(course=self.course, title='Midterm', starts_at=now + timedelta(days=1))
        Exam.objects.create(course=self.course, title='Final', starts_at=now + timedelta(days=20))
        Exam.objects.create(course=self.course, title='Past quiz', starts_at=now - timedelta(hours=2))

        payload = self.client.get(reverse('api:dashboard')).json()
        self.assertEqual(
            [(item['kind'], item['title']) for item in payload['upcoming']],
            [
                ('assignment', 'Late essay'),
                ('exam', 'Midterm'),
                ('assignment', 'Sprint review'),
                ('exam', 'Final'),
                ('assignment', 'Someday reading'),
            ],
        )
        self.assertEqual(payload['metrics']['due_this_week'], 2)
        self.assertEqual(payload['metrics']['overdue'], 1)

    def test_exam_ownership_and_auth_are_enforced(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='pass12345')
        Exam.objects.create(course=self.course, title='Midterm', starts_at=timezone.now() + timedelta(days=3))
        self.client.force_login(other)
        response = self.json_post(reverse('api:course_exams', args=[self.course.pk]), {
            'title': 'Sneaky', 'starts_at': '2026-11-05T14:00',
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse('api:dashboard')).json()['upcoming'], [])
        self.client.logout()
        response = self.json_post(reverse('api:course_exams', args=[self.course.pk]), {
            'title': 'Sneaky', 'starts_at': '2026-11-05T14:00',
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(Exam.objects.values_list('title', flat=True)), ['Midterm'])

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
