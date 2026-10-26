from django.test import TestCase

from .forms import SignUpForm
from .models import User


class SignUpFormTests(TestCase):
    def form_data(self, **overrides):
        data = {
            'email': 'student@nyu.edu',
            'password1': 'a-strong-test-password-2026',
            'password2': 'a-strong-test-password-2026',
        }
        data.update(overrides)
        return data

    def test_valid_signup_normalizes_email_and_populates_username(self):
        form = SignUpForm(self.form_data(email='STUDENT@NYU.EDU'))

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, 'student@nyu.edu')
        self.assertEqual(user.username, 'student@nyu.edu')
        self.assertTrue(user.check_password('a-strong-test-password-2026'))

    def test_duplicate_email_is_case_insensitive(self):
        User.objects.create_user(
            username='student@nyu.edu',
            email='student@nyu.edu',
            password='a-strong-test-password-2026',
        )

        form = SignUpForm(self.form_data(email='STUDENT@NYU.EDU'))

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['email'],
            ['An account with this email already exists.'],
        )

    def test_rejects_invalid_email(self):
        form = SignUpForm(self.form_data(email='not-an-email'))

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_rejects_non_nyu_email(self):
        form = SignUpForm(self.form_data(email='student@gmail.com'))

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['email'],
            ['Please sign up with your NYU email address (@nyu.edu).'],
        )

    def test_accepts_nyu_school_subdomain_email(self):
        form = SignUpForm(self.form_data(email='STUDENT@STERN.NYU.EDU'))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['email'], 'student@stern.nyu.edu')

    def test_rejects_a_lookalike_domain(self):
        form = SignUpForm(self.form_data(email='student@notnyu.edu'))

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['email'],
            ['Please sign up with your NYU email address (@nyu.edu).'],
        )

    def test_rejects_mismatched_passwords(self):
        form = SignUpForm(self.form_data(password2='a-different-password-2026'))

        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_rejects_weak_password(self):
        form = SignUpForm(self.form_data(password1='12345678', password2='12345678'))

        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)
