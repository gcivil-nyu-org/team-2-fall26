import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class PrivacySettingsTests(TestCase):
    """#31: a student chooses what other students can see."""

    def setUp(self):
        self.user = User.objects.create_user(username='student@nyu.edu', email='student@nyu.edu', password='test123')
        self.url = reverse('api:profile_privacy')

    def put(self, body):
        return self.client.put(self.url, json.dumps(body), content_type='application/json')

    def test_requires_login(self):
        self.assertEqual(self.put({'show_bio': False}).status_code, 401)

    def test_only_put_is_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 405)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_everything_is_visible_by_default(self):
        self.client.force_login(self.user)
        user = self.client.get(reverse('api:profile')).json()['user']
        self.assertEqual(
            (user['show_email'], user['show_bio'], user['show_profile_picture']), (True, True, True),
        )

    def test_hide_and_show_each_field(self):
        self.client.force_login(self.user)
        for field in ('show_email', 'show_bio', 'show_profile_picture'):
            response = self.put({field: False})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['user'][field])
            self.user.refresh_from_db()
            self.assertFalse(getattr(self.user, field))
            self.assertTrue(self.put({field: True}).json()['user'][field])

    def test_a_field_left_out_keeps_its_current_value(self):
        self.user.show_email = False
        self.user.save()
        self.client.force_login(self.user)
        user = self.put({'show_bio': False}).json()['user']
        self.assertFalse(user['show_email'])
        self.assertFalse(user['show_bio'])
        self.assertTrue(user['show_profile_picture'])

    def test_settings_persist_across_requests(self):
        self.client.force_login(self.user)
        self.put({'show_email': False, 'show_bio': False, 'show_profile_picture': False})
        user = self.client.get(reverse('api:profile')).json()['user']
        self.assertEqual(
            (user['show_email'], user['show_bio'], user['show_profile_picture']), (False, False, False),
        )

    def test_rejects_values_that_are_not_true_or_false(self):
        self.client.force_login(self.user)
        for bad in ('false', 'yes', 0, 1, None, []):
            response = self.put({'show_bio': bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('show_bio', response.json()['errors'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.show_bio)

    def test_a_bad_value_changes_nothing(self):
        self.client.force_login(self.user)
        response = self.put({'show_email': False, 'show_bio': 'nope'})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.show_email)

    def test_rejects_malformed_json_and_non_objects(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.put(self.url, '{nope', content_type='application/json').status_code, 400)
        self.assertEqual(self.put([True]).status_code, 400)

    def test_only_changes_the_signed_in_students_own_settings(self):
        other = User.objects.create_user(username='other@nyu.edu', email='other@nyu.edu', password='test123')
        self.client.force_login(self.user)
        self.put({'show_email': False, 'user': other.pk, 'id': other.pk})
        other.refresh_from_db()
        self.assertTrue(other.show_email)

    def test_does_not_touch_name_or_bio(self):
        self.user.first_name, self.user.bio = 'Jane', 'Hello'
        self.user.save()
        self.client.force_login(self.user)
        self.put({'show_bio': False, 'first_name': 'Hacker', 'bio': 'changed'})
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.bio), ('Jane', 'Hello'))

    def test_hiding_the_bio_keeps_it_for_the_owner(self):
        self.user.bio = 'My bio'
        self.user.save()
        self.client.force_login(self.user)
        self.put({'show_bio': False})
        self.assertEqual(self.client.get(reverse('api:profile')).json()['user']['bio'], 'My bio')
