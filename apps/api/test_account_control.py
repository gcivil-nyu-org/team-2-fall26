import json
from datetime import timedelta

from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.coursework.models import Assignment, Course, Exam


class AccountControlTests(TestCase):
    password = 'Account-control-test-4826!'

    def setUp(self):
        self.user = User.objects.create_user(username='account@nyu.edu', email='account@nyu.edu', password=self.password)
        self.other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password=self.password)
        self.course = Course.objects.create(owner=self.user, name='My course', semester='Fall 2026')
        self.assignment = Assignment.objects.create(course=self.course, title='My assignment')
        self.exam = Exam.objects.create(course=self.course, title='My exam', starts_at=timezone.now() + timedelta(days=2))
        self.other_course = Course.objects.create(owner=self.other, name='Other course', semester='Fall 2026')
        self.other_assignment = Assignment.objects.create(course=self.other_course, title='Other assignment')
        self.other_exam = Exam.objects.create(course=self.other_course, title='Other exam', starts_at=timezone.now())
        self.client.force_login(self.user)

    def act(self, action, client=None, **overrides):
        data = {'current_password': self.password, 'confirmation': action.upper()}
        data.update(overrides)
        client = client or self.client
        if action == 'delete':
            return client.delete(reverse('api:account_delete'), json.dumps(data), content_type='application/json')
        return client.post(reverse('api:account_deactivate'), json.dumps(data), content_type='application/json')

    def assert_other_account_unchanged(self):
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_active)
        self.assertTrue(Course.objects.filter(pk=self.other_course.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.other_assignment.pk).exists())
        self.assertTrue(Exam.objects.filter(pk=self.other_exam.pk).exists())

    def test_deactivation_keeps_data_and_signs_out(self):
        response = self.act('deactivate')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.check_password(self.password))
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertFalse(self.client.get(reverse('api:session')).json()['authenticated'])
        self.assertEqual(self.client.get(reverse('api:dashboard')).status_code, 401)
        self.assert_other_account_unchanged()

    def test_deactivated_account_cannot_log_in(self):
        self.act('deactivate')
        response = self.client.post(reverse('api:login'), json.dumps({'email': self.user.email, 'password': self.password}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.client.get(reverse('api:session')).json()['authenticated'])

    def test_deactivation_retires_other_sessions_even_after_admin_reactivation(self):
        second = Client()
        second.force_login(self.user)
        token = default_token_generator.make_token(self.user)
        self.act('deactivate')
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, token))
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        self.assertFalse(second.get(reverse('api:session')).json()['authenticated'])
        self.assertTrue(self.client.login(username=self.user.username, password=self.password))

    def test_delete_removes_only_own_account_and_coursework(self):
        second = Client()
        second.force_login(self.user)
        response = self.act('delete', user_id=self.other.pk, owner=self.other.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())
        self.assertFalse(Assignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertFalse(Exam.objects.filter(pk=self.exam.pk).exists())
        self.assertFalse(self.client.get(reverse('api:session')).json()['authenticated'])
        self.assertFalse(second.get(reverse('api:session')).json()['authenticated'])
        self.assert_other_account_unchanged()

    def test_deactivate_ignores_target_account_in_payload(self):
        self.assertEqual(self.act('deactivate', user_id=self.other.pk).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assert_other_account_unchanged()

    def test_wrong_or_missing_password_prevents_both_actions(self):
        for action in ['deactivate', 'delete']:
            for password in ['', 'wrong-password']:
                with self.subTest(action=action, password=password):
                    response = self.act(action, current_password=password)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('current_password', response.json()['errors'])
                    self.user.refresh_from_db()
                    self.assertTrue(self.user.is_active)
                    self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())

    def test_exact_confirmation_is_required(self):
        for action in ['deactivate', 'delete']:
            for confirmation in ['', action, 'OTHER']:
                with self.subTest(action=action, confirmation=confirmation):
                    response = self.act(action, confirmation=confirmation)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('confirmation', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_anonymous_requests_cannot_modify_accounts(self):
        self.client.logout()
        for action in ['deactivate', 'delete']:
            self.assertEqual(self.act(action).status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_get_requests_cannot_modify_accounts(self):
        for name in ['account_deactivate', 'account_delete']:
            self.assertEqual(self.client.get(reverse(f'api:{name}')).status_code, 405)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_malformed_json_and_field_types_are_rejected(self):
        for body in ['invalid', '[]', 'null', '{"confirmation": "DELETE", "current_password": []}', '{"confirmation": true}']:
            with self.subTest(body=body):
                response = self.client.delete(reverse('api:account_delete'), body, content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_both_actions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for action in ['deactivate', 'delete']:
            self.assertEqual(self.act(action, client=client).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_action_accepts_valid_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(reverse('api:session'))
        response = client.post(reverse('api:account_deactivate'), json.dumps({'current_password': self.password, 'confirmation': 'DEACTIVATE'}), content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
