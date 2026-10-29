import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .forms import ProfileForm, ProfilePictureForm, SignUpForm
from .models import User

SMALL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04'
    b'\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
    b'\x02\x4c\x01\x00\x3b'
)


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


class ProfileFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )

    def test_updates_first_and_last_name(self):
        form = ProfileForm({'first_name': 'Jane', 'last_name': 'Doe'}, instance=self.user)

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Doe')

    def test_requires_first_name(self):
        form = ProfileForm({'first_name': '', 'last_name': 'Doe'}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['first_name'], ['First name is required.'])

    def test_requires_last_name(self):
        form = ProfileForm({'first_name': 'Jane', 'last_name': ''}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['last_name'], ['Last name is required.'])

    def test_does_not_change_email(self):
        form = ProfileForm({'first_name': 'Jane', 'last_name': 'Doe'}, instance=self.user)
        form.is_valid()
        user = form.save()

        self.assertEqual(user.email, 'student@nyu.edu')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProfilePictureFormTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username='student@nyu.edu', email='student@nyu.edu', password='testpass123',
        )

    def test_accepts_a_valid_image(self):
        picture = SimpleUploadedFile('avatar.gif', SMALL_GIF, content_type='image/gif')
        form = ProfilePictureForm({}, {'profile_picture': picture}, instance=self.user)

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_a_non_image_file(self):
        not_an_image = SimpleUploadedFile('notes.txt', b'just some text', content_type='text/plain')
        form = ProfilePictureForm({}, {'profile_picture': not_an_image}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('profile_picture', form.errors)

    @override_settings(MAX_PROFILE_PICTURE_SIZE=10)
    def test_rejects_an_oversized_image(self):
        picture = SimpleUploadedFile('avatar.gif', SMALL_GIF, content_type='image/gif')
        form = ProfilePictureForm({}, {'profile_picture': picture}, instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('profile_picture', form.errors)
