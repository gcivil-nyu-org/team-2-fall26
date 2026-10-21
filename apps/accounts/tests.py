from django.test import TestCase
from django.urls import reverse
from .models import User


class SignupTests(TestCase):
    def test_invalid_email_format_rejected(self):
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'not-an-email', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 0)

    def test_valid_signup_creates_account(self):
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 1)

    def test_signup_saves_first_and_last_name(self):
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        user = User.objects.get()
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Doe')

    def test_missing_first_name_rejected(self):
        response = self.client.post(reverse('accounts:signup'), {
            'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(response, 'This field is required.')

    def test_missing_last_name_rejected(self):
        response = self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(response, 'This field is required.')

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='testpass123')
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 1)

    def test_signup_logs_in_and_redirects_to_dashboard(self):
        response = self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertRedirects(response, reverse('accounts:dashboard'))

    def test_password_mismatch_rejected(self):
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': 'testpass123', 'password2': 'different456',
        })
        self.assertEqual(User.objects.count(), 0)

    def test_weak_password_rejected(self):
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'student@nyu.edu', 'password1': '12345678', 'password2': '12345678',
        })
        self.assertEqual(User.objects.count(), 0)

    def test_duplicate_email_rejected_case_insensitive(self):
        User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='testpass123')
        self.client.post(reverse('accounts:signup'), {
            'first_name': 'Jane', 'last_name': 'Doe',
            'email': 'STUDENT@NYU.edu', 'password1': 'testpass123', 'password2': 'testpass123',
        })
        self.assertEqual(User.objects.count(), 1)


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )

    def test_valid_login(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'student@nyu.edu', 'password': 'testpass123',
        })
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_is_case_insensitive_on_email(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'STUDENT@nyu.edu', 'password': 'testpass123',
        })
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_wrong_password_shows_one_generic_error(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'student@nyu.edu', 'password': 'wrongpass',
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(len(response.context['form'].non_field_errors()), 1)

    def test_session_persists_between_requests(self):
        self.client.login(username='student@nyu.edu', password='testpass123')
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_logout_requires_post(self):
        self.client.login(username='student@nyu.edu', password='testpass123')
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)  # GET is rejected

    def test_logout_ends_session(self):
        self.client.login(username='student@nyu.edu', password='testpass123')
        self.client.post(reverse('accounts:logout'))
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)  # bounced to login, session is gone

    def test_nonexistent_email_rejected(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'nobody@nyu.edu', 'password': 'testpass123',
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(len(response.context['form'].non_field_errors()), 1)

    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}"
        )
