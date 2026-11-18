import re
from datetime import timedelta
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.coursework.models import Course

from .forms import SignUpForm, validate_student_email
from .models import User

PASSWORD = 'a-strong-test-password-2026'


def make_user(email, **fields):
    fields.setdefault('password', PASSWORD)
    return User.objects.create_user(username=email, email=email, **fields)


# Admin pages link to Django's admin CSS. Where WhiteNoise is installed (CI,
# deployed environments) the project uses a manifest static-file storage that
# needs `collectstatic` first, so tests use the plain storage instead.
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AdminTestCase(TestCase):
    """#54: administrators manage student accounts from /admin/."""

    def setUp(self):
        self.root = User.objects.create_superuser(username='root@nyu.edu', email='root@nyu.edu', password=PASSWORD)
        self.sam = make_user('sam@nyu.edu', first_name='Sam', last_name='Lee', bio='CS junior')
        self.kim = make_user('kim@nyu.edu', first_name='Kim', last_name='Park')
        self.client.force_login(self.root)
        self.changelist = reverse('admin:accounts_user_changelist')

    def change_url(self, user):
        return reverse('admin:accounts_user_change', args=[user.pk])

    def delete_url(self, user):
        return reverse('admin:accounts_user_delete', args=[user.pk])

    def staff_with_permissions(self, email='staff@nyu.edu', codenames=('view_user', 'change_user', 'delete_user')):
        staff = make_user(email, is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label='accounts', codename__in=codenames))
        return staff

    def run_action(self, action, users, **extra):
        return self.client.post(
            self.changelist,
            {'action': action, '_selected_action': [user.pk for user in users], **extra},
            follow=True,
        )

    def messages(self, response):
        return [str(message) for message in response.context['messages']]

    def listed(self, response):
        # The accounts in the list itself. (The page header also names whoever
        # is signed in, so searching the whole page for an email proves little.)
        return {user.email for user in response.context['cl'].result_list}

    def edit(self, user, **overrides):
        data = {
            'email': user.email, 'first_name': user.first_name, 'last_name': user.last_name, 'bio': user.bio,
            'is_active': 'on' if user.is_active else '',
        }
        data.update(overrides)
        return self.client.post(self.change_url(user), data)


class AccessTests(AdminTestCase):
    def test_signed_out_visitors_are_sent_to_the_admin_login(self):
        self.client.logout()
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_a_student_cannot_open_the_account_list(self):
        self.client.force_login(self.sam)
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_without_account_permissions_get_nothing(self):
        staff = make_user('nopower@nyu.edu', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.changelist).status_code, 403)

    def test_the_admin_is_branded_for_semesterpilot(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'SemesterPilot administration')

    def test_nobody_can_create_accounts_here_because_students_sign_up_themselves(self):
        self.assertEqual(self.client.get(reverse('admin:accounts_user_add')).status_code, 403)
        self.assertNotContains(self.client.get(self.changelist), 'Add user')


class ModifyRequiresAuthorizationTests(AdminTestCase):
    """#54 AC: nobody can change an account without administrator authorization."""

    def attempt_everything(self):
        """Try to edit, deactivate, delete and send a reset for Sam, as whoever is signed in."""
        self.client.post(self.change_url(self.sam), {
            'email': 'hacked@nyu.edu', 'first_name': 'Hacked', 'last_name': '', 'bio': '', 'is_active': '',
        })
        self.client.post(self.changelist, {'action': 'deactivate_accounts', '_selected_action': [self.sam.pk]})
        self.client.post(self.changelist, {'action': 'send_password_reset', '_selected_action': [self.sam.pk]})
        self.client.post(self.changelist, {'action': 'delete_selected', '_selected_action': [self.sam.pk], 'post': 'yes'})
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})

    def assert_untouched(self):
        sam = User.objects.get(pk=self.sam.pk)
        self.assertEqual((sam.email, sam.first_name, sam.is_active), ('sam@nyu.edu', 'Sam', True))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.sam.pk)).exists())

    def test_signed_out_visitors_cannot_change_anything(self):
        self.client.logout()
        self.attempt_everything()
        self.assert_untouched()

    def test_a_signed_in_student_cannot_change_anything_including_their_own_status(self):
        self.client.force_login(self.kim)
        self.attempt_everything()
        self.client.post(self.change_url(self.kim), {'email': 'kim@nyu.edu', 'is_active': '', 'first_name': 'Kim'})
        self.assert_untouched()
        self.assertTrue(User.objects.get(pk=self.kim.pk).is_active)

    def test_staff_with_no_account_permissions_cannot_change_anything(self):
        self.client.force_login(make_user('nopower@nyu.edu', is_staff=True))
        self.attempt_everything()
        self.assert_untouched()

    def test_staff_who_can_only_view_cannot_edit_deactivate_or_delete(self):
        self.client.force_login(self.staff_with_permissions(codenames=('view_user',)))
        self.attempt_everything()
        self.assert_untouched()

    def test_a_deactivated_administrator_loses_access_to_the_admin(self):
        self.sam.is_staff = True
        self.sam.save()
        self.client.force_login(self.sam)
        self.sam.is_active = False
        self.sam.save()
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])


class AccountListTests(AdminTestCase):
    def test_lists_each_account_with_name_status_role_and_course_count(self):
        Course.objects.create(owner=self.sam, name='Algorithms', semester='Fall 2026')
        Course.objects.create(owner=self.sam, name='Databases', semester='Fall 2026')
        response = self.client.get(self.changelist)
        self.assertContains(response, 'sam@nyu.edu')
        self.assertContains(response, 'Sam Lee')
        html = response.content.decode()
        row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*sam@nyu\.edu(?:(?!</tr>).)*</tr>', html, re.S).group(0)
        self.assertIn('Student', row)
        self.assertIn('Active', row)
        self.assertRegex(row, r'>\s*2\s*<')

    def test_an_account_with_no_name_shows_a_dash_and_administrators_are_labelled(self):
        row_html = self.client.get(self.changelist).content.decode()
        root_row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*root@nyu\.edu(?:(?!</tr>).)*</tr>', row_html, re.S).group(0)
        self.assertIn('Administrator', root_row)
        self.assertIn('—', root_row)

    def test_a_deactivated_account_says_so(self):
        self.kim.is_active = False
        self.kim.save()
        html = self.client.get(self.changelist).content.decode()
        row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*kim@nyu\.edu(?:(?!</tr>).)*</tr>', html, re.S).group(0)
        self.assertIn('Deactivated', row)

    def test_search_by_email_first_name_or_last_name(self):
        for term, found, absent in [('sam@', 'sam@nyu.edu', 'kim@nyu.edu'), ('Kim', 'kim@nyu.edu', 'sam@nyu.edu'), ('Lee', 'sam@nyu.edu', 'kim@nyu.edu')]:
            with self.subTest(term):
                response = self.client.get(self.changelist, {'q': term})
                self.assertContains(response, found)
                self.assertNotContains(response, absent)

    def test_search_by_full_name(self):
        response = self.client.get(self.changelist, {'q': 'Sam Lee'})
        self.assertEqual(self.listed(response), {'sam@nyu.edu'})

    def test_search_ignores_case_and_finds_nothing_for_an_unknown_name(self):
        self.assertEqual(self.listed(self.client.get(self.changelist, {'q': 'KIM PARK'})), {'kim@nyu.edu'})
        self.assertEqual(self.listed(self.client.get(self.changelist, {'q': 'Nobody Here'})), set())

    def test_filter_by_active_status(self):
        self.kim.is_active = False
        self.kim.save()
        active = self.client.get(self.changelist, {'is_active__exact': '1'})
        self.assertContains(active, 'sam@nyu.edu')
        self.assertNotContains(active, 'kim@nyu.edu')
        inactive = self.client.get(self.changelist, {'is_active__exact': '0'})
        self.assertContains(inactive, 'kim@nyu.edu')
        self.assertNotContains(inactive, 'sam@nyu.edu')

    def test_filter_by_role(self):
        self.assertEqual(self.listed(self.client.get(self.changelist, {'role': 'student'})), {'sam@nyu.edu', 'kim@nyu.edu'})
        self.assertEqual(self.listed(self.client.get(self.changelist, {'role': 'admin'})), {'root@nyu.edu'})

    def test_filter_by_last_sign_in(self):
        self.sam.last_login = timezone.now() - timedelta(days=2)
        self.sam.save()
        self.kim.last_login = timezone.now() - timedelta(days=90)
        self.kim.save()
        third = make_user('never@nyu.edu')
        for value, present, absent in [
            ('never', 'never@nyu.edu', 'sam@nyu.edu'),
            ('recent', 'sam@nyu.edu', 'kim@nyu.edu'),
            ('stale', 'kim@nyu.edu', 'sam@nyu.edu'),
        ]:
            with self.subTest(value):
                response = self.client.get(self.changelist, {'signin': value})
                self.assertContains(response, present)
                self.assertNotContains(response, absent)
        self.assertNotContains(self.client.get(self.changelist, {'signin': 'never'}), third.email + 'x')

    def test_newest_accounts_come_first(self):
        html = self.client.get(self.changelist).content.decode()
        self.assertLess(html.index('kim@nyu.edu'), html.index('sam@nyu.edu'))

    def test_staff_who_are_not_superusers_only_see_students(self):
        staff = self.staff_with_permissions()
        self.client.force_login(staff)
        self.assertEqual(self.listed(self.client.get(self.changelist)), {'sam@nyu.edu', 'kim@nyu.edu'})

    def test_staff_cannot_open_an_administrators_account_by_url(self):
        staff = self.staff_with_permissions()
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.change_url(self.root), follow=True).redirect_chain[-1][0].split('?')[0], reverse('admin:index'))

    def test_superusers_see_administrators_too(self):
        self.assertIn('root@nyu.edu', self.listed(self.client.get(self.changelist)))


class EditAccountTests(AdminTestCase):
    def test_the_form_shows_profile_details_but_never_the_password(self):
        response = self.client.get(self.change_url(self.sam))
        self.assertContains(response, 'sam@nyu.edu')
        self.assertContains(response, 'CS junior')
        self.assertNotContains(response, 'pbkdf2')
        self.assertNotContains(response, 'name="password"')
        self.assertNotContains(response, 'user_permissions')

    def test_there_is_no_page_for_setting_a_students_password(self):
        response = self.client.get(f'{self.change_url(self.sam)}password/', follow=True)
        self.assertNotContains(response, 'new_password')
        self.assertNotContains(response, 'password1')

    def test_an_administrator_can_correct_a_name_and_bio(self):
        response = self.edit(self.sam, first_name='Samuel', last_name='Leigh', bio='Updated')
        self.assertEqual(response.status_code, 302)
        self.sam.refresh_from_db()
        self.assertEqual((self.sam.first_name, self.sam.last_name, self.sam.bio), ('Samuel', 'Leigh', 'Updated'))

    def test_a_corrected_email_is_lower_cased_and_the_student_can_sign_in_with_it(self):
        self.edit(self.sam, email='Samuel.Lee@NYU.edu')
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.email, 'samuel.lee@nyu.edu')
        self.assertEqual(self.sam.username, 'samuel.lee@nyu.edu')
        self.client.logout()
        response = self.client.post(
            reverse('api:login'), {'email': 'samuel.lee@nyu.edu', 'password': PASSWORD}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_an_administrators_separate_username_is_kept_when_their_details_are_edited(self):
        other_root = User.objects.create_superuser(username='sysadmin', email='sysadmin@nyu.edu', password=PASSWORD)
        self.edit(other_root, first_name='Pat')
        other_root.refresh_from_db()
        self.assertEqual((other_root.username, other_root.first_name), ('sysadmin', 'Pat'))
        self.edit(other_root, email='pat.admin@nyu.edu')
        other_root.refresh_from_db()
        self.assertEqual((other_root.username, other_root.email), ('sysadmin', 'pat.admin@nyu.edu'))

    def test_editing_other_details_leaves_a_students_username_alone(self):
        self.edit(self.sam, first_name='Samuel')
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.username, 'sam@nyu.edu')

    def test_the_old_email_stops_working_after_a_correction(self):
        self.edit(self.sam, email='samuel@nyu.edu')
        self.client.logout()
        response = self.client.post(
            reverse('api:login'), {'email': 'sam@nyu.edu', 'password': PASSWORD}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_an_email_already_in_use_is_rejected_whatever_its_case(self):
        for taken in ('kim@nyu.edu', 'KIM@nyu.edu'):
            with self.subTest(taken):
                response = self.edit(self.sam, email=taken)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'An account with this email already exists.')
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.email, 'sam@nyu.edu')

    def test_a_non_nyu_email_is_rejected(self):
        response = self.edit(self.sam, email='sam@gmail.com')
        self.assertContains(response, 'Please sign up with your NYU email address')
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.email, 'sam@nyu.edu')

    def test_a_blank_or_malformed_email_is_rejected(self):
        for bad in ('', 'not-an-email'):
            with self.subTest(bad):
                self.assertEqual(self.edit(self.sam, email=bad).status_code, 200)
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.email, 'sam@nyu.edu')

    def test_saving_without_changing_the_email_is_fine(self):
        self.assertEqual(self.edit(self.sam, first_name='Samantha').status_code, 302)

    def test_a_bio_over_300_characters_is_rejected(self):
        self.assertEqual(self.edit(self.sam, bio='x' * 301).status_code, 200)
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.bio, 'CS junior')

    def test_join_and_sign_in_dates_cannot_be_edited(self):
        joined = self.sam.date_joined
        self.edit(self.sam, date_joined='2000-01-01 00:00:00')
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.date_joined, joined)

    def test_role_and_permissions_cannot_be_changed_from_the_student_form(self):
        self.edit(self.sam, is_staff='on', is_superuser='on')
        self.sam.refresh_from_db()
        self.assertFalse(self.sam.is_staff)
        self.assertFalse(self.sam.is_superuser)

    def test_the_change_is_recorded_in_the_history(self):
        self.edit(self.sam, first_name='Samuel')
        entry = LogEntry.objects.get(object_id=str(self.sam.pk))
        self.assertEqual(entry.user, self.root)
        self.assertIn('First name', entry.get_change_message())
        self.assertContains(self.client.get(reverse('admin:accounts_user_history', args=[self.sam.pk])), 'root@nyu.edu')


class DeactivateTests(AdminTestCase):
    def test_unticking_active_deactivates_and_blocks_sign_in(self):
        self.edit(self.sam, is_active='')
        self.sam.refresh_from_db()
        self.assertFalse(self.sam.is_active)
        self.client.logout()
        response = self.client.post(
            reverse('api:login'), {'email': 'sam@nyu.edu', 'password': PASSWORD}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_signed_in_student_is_signed_out_when_deactivated(self):
        student = self.client_class()
        student.force_login(self.sam)
        self.assertEqual(student.get(reverse('api:session')).json()['authenticated'], True)
        self.edit(self.sam, is_active='')
        self.assertEqual(student.get(reverse('api:session')).json()['authenticated'], False)

    def test_reactivating_lets_them_sign_in_again_with_the_same_password(self):
        self.sam.is_active = False
        self.sam.save()
        self.edit(self.sam, is_active='on')
        self.client.logout()
        response = self.client.post(
            reverse('api:login'), {'email': 'sam@nyu.edu', 'password': PASSWORD}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_deactivating_keeps_all_of_the_students_data(self):
        Course.objects.create(owner=self.sam, name='Algorithms', semester='Fall 2026')
        self.run_action('deactivate_accounts', [self.sam])
        self.assertEqual(Course.objects.filter(owner=self.sam).count(), 1)

    def test_a_student_who_deactivated_themselves_can_be_reactivated_by_an_administrator(self):
        self.client.force_login(self.sam)
        self.client.post(
            reverse('api:account_deactivate'), {'current_password': PASSWORD, 'confirmation': 'DEACTIVATE'}, content_type='application/json',
        )
        self.sam.refresh_from_db()
        self.assertFalse(self.sam.is_active)
        self.client.force_login(self.root)
        self.run_action('reactivate_accounts', [self.sam])
        self.sam.refresh_from_db()
        self.assertTrue(self.sam.is_active)

    def test_deactivate_action_handles_many_accounts_and_reports_the_count(self):
        response = self.run_action('deactivate_accounts', [self.sam, self.kim])
        self.assertFalse(User.objects.filter(pk__in=[self.sam.pk, self.kim.pk], is_active=True).exists())
        self.assertIn('Deactivated 2 accounts.', self.messages(response))

    def test_deactivate_action_says_one_account_in_the_singular(self):
        response = self.run_action('deactivate_accounts', [self.sam])
        self.assertIn('Deactivated 1 account.', self.messages(response))

    def test_already_deactivated_accounts_are_left_alone(self):
        self.sam.is_active = False
        self.sam.save()
        response = self.run_action('deactivate_accounts', [self.sam])
        self.assertIn('Nothing to do for the selected accounts.', self.messages(response))
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.sam.pk)).exists())

    def test_reactivate_action(self):
        User.objects.filter(pk__in=[self.sam.pk, self.kim.pk]).update(is_active=False)
        response = self.run_action('reactivate_accounts', [self.sam, self.kim])
        self.assertFalse(User.objects.filter(pk__in=[self.sam.pk, self.kim.pk], is_active=False).exists())
        self.assertIn('Reactivated 2 accounts.', self.messages(response))

    def test_reactivating_active_accounts_does_nothing(self):
        response = self.run_action('reactivate_accounts', [self.sam])
        self.assertIn('Nothing to do for the selected accounts.', self.messages(response))

    def test_each_action_is_recorded_for_each_account(self):
        self.run_action('deactivate_accounts', [self.sam, self.kim])
        self.run_action('reactivate_accounts', [self.sam])
        sam_entries = LogEntry.objects.filter(object_id=str(self.sam.pk)).order_by('action_time')
        self.assertEqual([entry.change_message for entry in sam_entries], ['Deactivated account.', 'Reactivated account.'])
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.kim.pk)).count(), 1)
        self.assertEqual(LogEntry.objects.get(object_id=str(self.kim.pk)).user, self.root)


class SafetyRuleTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.other_root = User.objects.create_superuser(username='root2@nyu.edu', email='root2@nyu.edu', password=PASSWORD)

    def test_an_administrator_cannot_deactivate_their_own_account_with_the_action(self):
        response = self.run_action('deactivate_accounts', [self.root])
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)
        self.assertTrue(any('you cannot do this to your own account' in text for text in self.messages(response)))

    def test_the_rest_of_a_batch_still_goes_ahead_when_your_own_account_is_included(self):
        self.run_action('deactivate_accounts', [self.sam, self.root, self.kim])
        self.assertEqual(User.objects.filter(is_active=False).count(), 2)
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)

    def test_the_active_checkbox_is_locked_on_your_own_account(self):
        self.assertNotContains(self.client.get(self.change_url(self.root)), 'name="is_active"')
        self.edit(self.root, is_active='')
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)

    def test_the_active_checkbox_is_available_on_other_accounts(self):
        self.assertContains(self.client.get(self.change_url(self.sam)), 'name="is_active"')
        self.assertContains(self.client.get(self.change_url(self.other_root)), 'name="is_active"')

    def test_one_superuser_can_deactivate_another(self):
        self.run_action('deactivate_accounts', [self.other_root])
        self.other_root.refresh_from_db()
        self.assertFalse(self.other_root.is_active)

    def test_you_cannot_delete_your_own_account(self):
        self.assertEqual(self.client.get(self.delete_url(self.root)).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url(self.root), {'post': 'yes'}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())

    def test_one_superuser_can_delete_another(self):
        self.assertEqual(self.client.post(self.delete_url(self.other_root), {'post': 'yes'}).status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.other_root.pk).exists())

    def test_ordinary_staff_cannot_reach_other_administrators_to_deactivate_or_delete_them(self):
        staff = self.staff_with_permissions()
        self.client.force_login(staff)
        self.run_action('deactivate_accounts', [self.root, self.other_root])
        self.assertTrue(User.objects.filter(is_superuser=True, is_active=True).count() == 2)
        self.client.post(self.delete_url(self.root), {'post': 'yes'}, follow=True)
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())

    def test_ordinary_staff_cannot_deactivate_themselves_through_the_list(self):
        staff = self.staff_with_permissions()
        self.client.force_login(staff)
        self.run_action('deactivate_accounts', [staff])
        self.assertTrue(User.objects.get(pk=staff.pk).is_active)


class DeleteAccountTests(AdminTestCase):
    def test_deleting_shows_what_will_go_with_the_account_and_asks_to_confirm(self):
        Course.objects.create(owner=self.sam, name='Algorithms', semester='Fall 2026')
        response = self.client.get(self.delete_url(self.sam))
        self.assertContains(response, 'Are you sure')
        self.assertContains(response, 'Algorithms')
        self.assertTrue(User.objects.filter(pk=self.sam.pk).exists())

    def test_confirming_deletes_the_account_and_everything_it_owns(self):
        course = Course.objects.create(owner=self.sam, name='Algorithms', semester='Fall 2026')
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})
        self.assertFalse(User.objects.filter(pk=self.sam.pk).exists())
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())

    def test_other_students_are_untouched(self):
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})
        self.assertTrue(User.objects.filter(pk=self.kim.pk).exists())

    def test_the_deletion_is_recorded(self):
        pk = self.sam.pk
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})
        entry = LogEntry.objects.get(object_id=str(pk))
        self.assertEqual(entry.user, self.root)
        self.assertEqual(entry.object_repr, 'sam@nyu.edu')

    def test_bulk_delete_asks_first_then_deletes(self):
        asked = self.run_action('delete_selected', [self.sam, self.kim])
        self.assertContains(asked, 'Are you sure')
        self.assertEqual(User.objects.filter(email__in=['sam@nyu.edu', 'kim@nyu.edu']).count(), 2)
        self.run_action('delete_selected', [self.sam, self.kim], post='yes')
        self.assertEqual(User.objects.filter(email__in=['sam@nyu.edu', 'kim@nyu.edu']).count(), 0)

    def test_bulk_delete_refuses_when_your_own_account_is_selected(self):
        warned = self.run_action('delete_selected', [self.sam, self.root])
        self.assertContains(warned, 'Cannot delete')
        response = self.client.post(
            self.changelist,
            {'action': 'delete_selected', '_selected_action': [self.sam.pk, self.root.pk], 'post': 'yes'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.sam.pk).exists())

    def test_staff_without_delete_permission_cannot_delete(self):
        staff = self.staff_with_permissions(codenames=('view_user', 'change_user'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.delete_url(self.sam)).status_code, 403)

    def test_staff_with_delete_permission_can_delete_a_student(self):
        staff = self.staff_with_permissions()
        self.client.force_login(staff)
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})
        self.assertFalse(User.objects.filter(pk=self.sam.pk).exists())


class PasswordResetActionTests(AdminTestCase):
    def test_sends_the_student_a_working_reset_link_and_never_shows_a_password(self):
        response = self.run_action('send_password_reset', [self.sam], HTTP_HOST='testserver')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['sam@nyu.edu'])
        self.assertIn('administrator', mail.outbox[0].body)
        self.assertIn('Sent 1 password reset email.', self.messages(response))
        uid, token = re.search(r'/app/reset-password/([^/\s]+)/([^/\s]+)', mail.outbox[0].body).groups()
        confirm = self.client.post(
            reverse('api:password_reset_confirm'),
            {'uid': uid, 'token': token, 'password': 'brand-new-pass-456!', 'password_confirm': 'brand-new-pass-456!'},
            content_type='application/json',
        )
        self.assertEqual(confirm.status_code, 200)

    def test_the_link_is_built_from_the_current_site(self):
        self.run_action('send_password_reset', [self.sam])
        self.assertIn('http://testserver/app/reset-password/', mail.outbox[0].body)

    def test_several_accounts_get_one_email_each(self):
        response = self.run_action('send_password_reset', [self.sam, self.kim])
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['kim@nyu.edu', 'sam@nyu.edu'])
        self.assertIn('Sent 2 password reset emails.', self.messages(response))

    def test_a_deactivated_account_is_skipped_with_an_explanation(self):
        self.sam.is_active = False
        self.sam.save()
        response = self.run_action('send_password_reset', [self.sam])
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(any('reactivate it first' in text for text in self.messages(response)))

    def test_a_broken_mail_server_gives_a_warning_not_an_error_page(self):
        with mock.patch('apps.accounts.password_reset.send_mail', side_effect=OSError('smtp unreachable')):
            response = self.run_action('send_password_reset', [self.sam])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('could not be sent' in text for text in self.messages(response)))
        self.assertFalse(LogEntry.objects.filter(object_id=str(self.sam.pk)).exists())

    def test_one_failure_does_not_stop_the_rest(self):
        real = mail.send_mail
        calls = {'n': 0}

        def flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                raise OSError('smtp unreachable')
            return real(*args, **kwargs)

        with mock.patch('apps.accounts.password_reset.send_mail', side_effect=flaky):
            self.run_action('send_password_reset', [self.sam, self.kim])
        self.assertEqual(len(mail.outbox), 1)

    def test_the_send_is_recorded_in_the_history(self):
        self.run_action('send_password_reset', [self.sam])
        self.assertEqual(LogEntry.objects.get(object_id=str(self.sam.pk)).change_message, 'Sent password reset email.')

    def test_the_token_is_valid_for_that_student_only(self):
        self.run_action('send_password_reset', [self.sam])
        token = re.search(r'/app/reset-password/[^/\s]+/([^/\s]+)', mail.outbox[0].body).group(1)
        self.assertTrue(default_token_generator.check_token(self.sam, token))
        self.assertFalse(default_token_generator.check_token(self.kim, token))


class EmailRuleTests(TestCase):
    def test_validate_student_email_lowercases_and_accepts_nyu_addresses(self):
        self.assertEqual(validate_student_email('Sam@NYU.edu'), 'sam@nyu.edu')
        self.assertEqual(validate_student_email('sam@cs.nyu.edu'), 'sam@cs.nyu.edu')

    def test_it_rejects_other_domains_including_look_alikes(self):
        from django import forms
        for bad in ('sam@gmail.com', 'sam@notnyu.edu', 'sam@nyu.edu.evil.com'):
            with self.subTest(bad), self.assertRaises(forms.ValidationError):
                validate_student_email(bad)

    def test_it_rejects_an_email_in_use_unless_it_belongs_to_the_account_being_edited(self):
        from django import forms
        sam = make_user('sam@nyu.edu')
        with self.assertRaises(forms.ValidationError):
            validate_student_email('SAM@nyu.edu')
        self.assertEqual(validate_student_email('sam@nyu.edu', exclude_pk=sam.pk), 'sam@nyu.edu')

    def test_sign_up_still_follows_the_same_rule(self):
        make_user('sam@nyu.edu')
        form = SignUpForm({'email': 'SAM@nyu.edu', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertFalse(form.is_valid())
        self.assertIn('An account with this email already exists.', form.errors['email'])
