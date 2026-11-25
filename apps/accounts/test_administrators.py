import re

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.urls import reverse

from .administrators import (
    ADMIN_GROUP_NAME, ADMIN_PERMISSIONS, REPORT_PERMISSIONS, access_level, administrator_group, can_manage_administrators,
)
from .models import User
from .test_admin import PASSWORD, AdminTestCase, make_user

GRANT = 'grant_admin_access'
REVOKE = 'revoke_admin_access'


class AdministratorAccessTestCase(AdminTestCase):
    """#60: super administrators decide who has administrator access."""

    def setUp(self):
        super().setUp()
        self.lee = make_user('lee@nyu.edu', first_name='Lee', last_name='Ng')

    def signed_in_as(self, user):
        client = Client()
        client.force_login(user)
        return client

    def make_administrator(self, user):
        self.run_action(GRANT, [user])
        user.refresh_from_db()
        return user

    def history(self, user):
        return list(LogEntry.objects.filter(object_id=str(user.pk)).values_list('change_message', flat=True))

    def role_filter(self, value):
        return self.client.get(self.changelist, {'role': value})


class ViewAdministratorsTests(AdministratorAccessTestCase):
    """AC: I can view users with administrator access."""

    def test_the_administrators_filter_lists_administrators_and_not_students(self):
        admin = self.make_administrator(self.sam)
        listed = self.listed(self.role_filter('admin'))
        self.assertEqual(listed, {self.root.email, admin.email})

    def test_the_super_administrators_filter_lists_only_super_administrators(self):
        self.make_administrator(self.sam)
        self.assertEqual(self.listed(self.role_filter('super')), {self.root.email})

    def test_the_students_filter_leaves_administrators_out(self):
        self.make_administrator(self.sam)
        self.assertEqual(self.listed(self.role_filter('student')), {self.kim.email, self.lee.email})

    def test_the_list_says_what_level_of_access_each_account_has(self):
        self.make_administrator(self.sam)
        levels = {user.email: access_level(user) for user in self.client.get(self.changelist).context['cl'].result_list}
        self.assertEqual(levels, {
            'root@nyu.edu': 'Super administrator', 'sam@nyu.edu': 'Administrator',
            'kim@nyu.edu': 'Student', 'lee@nyu.edu': 'Student',
        })
        html = self.client.get(self.changelist).content.decode()
        for label in ('Super administrator', 'Administrator', 'Student'):
            self.assertIn(f'<td class="field-role">{label}</td>', html)

    def tabs(self, response):
        return [(tab['label'], tab['count'], tab['current']) for tab in response.context['access_tabs']]

    def test_quick_links_show_how_many_accounts_of_each_kind(self):
        self.make_administrator(self.sam)
        response = self.client.get(self.changelist)
        self.assertEqual(self.tabs(response), [
            ('All accounts', 4, True), ('Students', 2, False),
            ('Administrators', 2, False), ('Super administrators', 1, False),
        ])
        html = response.content.decode()
        for label in ('All accounts', 'Students', 'Administrators', 'Super administrators'):
            self.assertIn(f'{label} <span>', html)
        self.assertIn('href="?role=admin"', html)

    def test_the_quick_link_for_the_current_list_is_marked(self):
        self.assertEqual([t[2] for t in self.tabs(self.role_filter('admin'))], [False, False, True, False])
        self.assertEqual([t[2] for t in self.tabs(self.client.get(self.changelist))], [True, False, False, False])
        nav = re.search(r'<nav class="access-tabs".*?</nav>', self.role_filter('super').content.decode(), re.S).group(0)
        self.assertEqual(nav.count('aria-current="page"'), 1)
        self.assertRegex(nav, r'aria-current="page">Super administrators')

    def test_the_counts_follow_grants_and_revokes(self):
        self.run_action(GRANT, [self.sam, self.kim])
        self.assertEqual(self.tabs(self.client.get(self.changelist))[2][1], 3)
        self.run_action(REVOKE, [self.kim])
        self.assertEqual(self.tabs(self.client.get(self.changelist))[2][1], 2)

    def test_ordinary_administrators_get_no_quick_links_and_no_role_filter(self):
        self.make_administrator(self.sam)
        response = self.signed_in_as(self.sam).get(self.changelist)
        self.assertNotIn('access_tabs', response.context)
        html = response.content.decode()
        self.assertNotIn('access-tabs', html)
        self.assertNotIn('role=admin', html)

    def test_the_filter_is_offered_in_the_sidebar(self):
        html = self.client.get(self.changelist).content.decode()
        self.assertIn('role=admin', html)
        self.assertIn('role=super', html)

    def test_a_student_made_administrator_by_other_means_is_listed_too(self):
        # e.g. someone marked as staff in the shell, outside this page.
        User.objects.filter(pk=self.kim.pk).update(is_staff=True)
        self.assertIn('kim@nyu.edu', self.listed(self.role_filter('admin')))


class GrantAccessTests(AdministratorAccessTestCase):
    """AC: I can grant administrator access to an authorized user."""

    def test_granting_makes_a_student_an_administrator(self):
        response = self.run_action(GRANT, [self.sam])
        self.sam.refresh_from_db()
        self.assertTrue(self.sam.is_staff)
        self.assertFalse(self.sam.is_superuser)
        self.assertIn('Granted administrator access to 1 account.', self.messages(response))

    def test_granting_adds_the_account_to_the_administrators_group(self):
        self.make_administrator(self.sam)
        self.assertTrue(self.sam.groups.filter(name=ADMIN_GROUP_NAME).exists())

    def test_the_group_gives_exactly_the_student_account_and_report_permissions(self):
        self.make_administrator(self.sam)
        group = Group.objects.get(name=ADMIN_GROUP_NAME)
        self.assertEqual(
            set(group.permissions.values_list('codename', flat=True)), set(ADMIN_PERMISSIONS) | set(REPORT_PERMISSIONS),
        )
        self.assertEqual({p.content_type.model for p in group.permissions.all()}, {'user', 'contentreport'})

    def test_the_group_is_put_right_even_if_someone_changed_it(self):
        group = administrator_group()
        group.permissions.add(Permission.objects.get(codename='add_group'))
        group.permissions.remove(Permission.objects.get(codename='delete_user'))
        self.make_administrator(self.sam)
        self.assertEqual(
            set(Group.objects.get(name=ADMIN_GROUP_NAME).permissions.values_list('codename', flat=True)),
            set(ADMIN_PERMISSIONS) | set(REPORT_PERMISSIONS),
        )

    def test_several_accounts_can_be_granted_at_once(self):
        response = self.run_action(GRANT, [self.sam, self.kim])
        self.assertTrue(User.objects.get(pk=self.sam.pk).is_staff)
        self.assertTrue(User.objects.get(pk=self.kim.pk).is_staff)
        self.assertEqual(Group.objects.filter(name=ADMIN_GROUP_NAME).count(), 1)
        self.assertIn('Granted administrator access to 2 accounts.', self.messages(response))

    def test_a_new_administrator_can_sign_in_and_manage_students(self):
        self.make_administrator(self.sam)
        client = self.signed_in_as(self.sam)
        self.assertEqual(client.get(self.changelist).status_code, 200)
        response = client.post(
            self.change_url(self.kim),
            {'email': 'kim@nyu.edu', 'first_name': 'Kimberly', 'last_name': 'Park', 'bio': '', 'is_active': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(pk=self.kim.pk).first_name, 'Kimberly')

    def test_a_new_administrator_sees_students_only(self):
        self.make_administrator(self.sam)
        self.assertEqual(
            self.listed(self.signed_in_as(self.sam).get(self.changelist)), {'kim@nyu.edu', 'lee@nyu.edu'},
        )

    def test_a_granted_account_stays_a_working_student_account(self):
        self.make_administrator(self.sam)
        self.assertTrue(Client().login(username='sam@nyu.edu', password=PASSWORD))
        self.assertEqual(User.objects.get(pk=self.sam.pk).email, 'sam@nyu.edu')

    def test_granting_is_recorded_in_the_accounts_history(self):
        self.make_administrator(self.sam)
        self.assertIn('Granted administrator access.', self.history(self.sam))
        response = self.client.get(reverse('admin:accounts_user_history', args=[self.sam.pk]))
        self.assertContains(response, 'Granted administrator access.')

    def test_a_deactivated_account_cannot_be_granted_access(self):
        User.objects.filter(pk=self.sam.pk).update(is_active=False)
        response = self.run_action(GRANT, [self.sam])
        self.assertFalse(User.objects.get(pk=self.sam.pk).is_staff)
        self.assertTrue(any('sam@nyu.edu' in m and 'deactivated' in m for m in self.messages(response)))
        self.assertEqual(self.history(self.sam), [])

    def test_granting_again_changes_nothing_and_says_so(self):
        self.make_administrator(self.sam)
        response = self.run_action(GRANT, [self.sam])
        self.assertTrue(any('already has administrator access' in m for m in self.messages(response)))
        self.assertEqual(self.history(self.sam), ['Granted administrator access.'])
        self.assertEqual(self.sam.groups.count(), 1)

    def test_a_staff_account_made_outside_the_admin_gets_its_permissions_when_granted(self):
        # Marked as staff in the shell: it can sign in but sees nothing until
        # it joins the Administrators group.
        User.objects.filter(pk=self.sam.pk).update(is_staff=True)
        client = self.signed_in_as(self.sam)
        self.assertEqual(client.get(self.changelist).status_code, 403)
        response = self.run_action(GRANT, [self.sam])
        self.assertIn('Granted administrator access to 1 account.', self.messages(response))
        self.assertEqual(client.get(self.changelist).status_code, 200)
        self.assertEqual(self.sam.groups.count(), 1)

    def test_a_super_administrator_is_not_regranted(self):
        other = User.objects.create_superuser(username='boss@nyu.edu', email='boss@nyu.edu', password=PASSWORD)
        response = self.run_action(GRANT, [other])
        self.assertTrue(any('boss@nyu.edu' in m for m in self.messages(response)))
        self.assertFalse(other.groups.exists())

    def test_one_skipped_account_does_not_stop_the_others(self):
        User.objects.filter(pk=self.sam.pk).update(is_active=False)
        response = self.run_action(GRANT, [self.sam, self.kim])
        self.assertTrue(User.objects.get(pk=self.kim.pk).is_staff)
        self.assertFalse(User.objects.get(pk=self.sam.pk).is_staff)
        self.assertIn('Granted administrator access to 1 account.', self.messages(response))


class RevokeAccessTests(AdministratorAccessTestCase):
    """AC: I can revoke administrator access when necessary."""

    def setUp(self):
        super().setUp()
        self.make_administrator(self.sam)

    def test_revoking_returns_the_account_to_a_student(self):
        response = self.run_action(REVOKE, [self.sam])
        self.sam.refresh_from_db()
        self.assertFalse(self.sam.is_staff)
        self.assertFalse(self.sam.groups.exists())
        self.assertEqual(access_level(self.sam), 'Student')
        self.assertIn('Revoked administrator access from 1 account.', self.messages(response))

    def test_revoking_takes_effect_on_the_next_click_even_if_signed_in(self):
        client = self.signed_in_as(self.sam)
        self.assertEqual(client.get(self.changelist).status_code, 200)
        self.run_action(REVOKE, [self.sam])
        response = client.get(self.changelist)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
        self.assertEqual(client.get(reverse('admin:index')).status_code, 302)

    def test_a_revoked_account_keeps_its_student_account(self):
        self.run_action(REVOKE, [self.sam])
        sam = User.objects.get(pk=self.sam.pk)
        self.assertTrue(sam.is_active)
        self.assertEqual((sam.email, sam.first_name), ('sam@nyu.edu', 'Sam'))
        self.assertTrue(Client().login(username='sam@nyu.edu', password=PASSWORD))

    def test_revoking_several_at_once(self):
        self.make_administrator(self.kim)
        response = self.run_action(REVOKE, [self.sam, self.kim])
        self.assertFalse(User.objects.filter(pk__in=[self.sam.pk, self.kim.pk], is_staff=True).exists())
        self.assertIn('Revoked administrator access from 2 accounts.', self.messages(response))

    def test_revoking_is_recorded_in_the_accounts_history(self):
        self.run_action(REVOKE, [self.sam])
        self.assertEqual(self.history(self.sam), ['Revoked administrator access.', 'Granted administrator access.'])

    def test_access_can_be_granted_again_after_it_was_revoked(self):
        self.run_action(REVOKE, [self.sam])
        self.run_action(GRANT, [self.sam])
        sam = User.objects.get(pk=self.sam.pk)
        self.assertTrue(sam.is_staff)
        self.assertEqual(list(sam.groups.values_list('name', flat=True)), [ADMIN_GROUP_NAME])
        self.assertEqual(self.signed_in_as(sam).get(self.changelist).status_code, 200)

    def test_a_deactivated_administrator_can_still_be_revoked(self):
        User.objects.filter(pk=self.sam.pk).update(is_active=False)
        self.run_action(REVOKE, [self.sam])
        self.assertFalse(User.objects.get(pk=self.sam.pk).is_staff)

    def test_revoking_a_student_does_nothing(self):
        response = self.run_action(REVOKE, [self.kim])
        self.assertEqual(self.history(self.kim), [])
        self.assertIn('Nothing to do for the selected accounts.', self.messages(response))

    def test_a_super_administrator_cannot_be_revoked_here(self):
        other = User.objects.create_superuser(username='boss@nyu.edu', email='boss@nyu.edu', password=PASSWORD)
        response = self.run_action(REVOKE, [other])
        other.refresh_from_db()
        self.assertTrue(other.is_staff and other.is_superuser)
        self.assertTrue(any('boss@nyu.edu' in m and 'super administrators' in m for m in self.messages(response)))
        self.assertEqual(self.history(other), [])

    def test_you_cannot_revoke_your_own_access(self):
        # Only super administrators can revoke, so the signed-in account is
        # always a super administrator here.
        response = self.run_action(REVOKE, [self.root])
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_staff and self.root.is_superuser)
        self.assertTrue(any('your own account' in m for m in self.messages(response)))

    def test_at_least_one_active_super_administrator_always_remains(self):
        self.run_action(REVOKE, [self.root, self.sam])
        self.assertTrue(User.objects.filter(is_superuser=True, is_active=True).exists())


class AccessRestrictionTests(AdministratorAccessTestCase):
    """AC: administrator-only features are inaccessible without administrator privileges."""

    def setUp(self):
        super().setUp()
        self.make_administrator(self.sam)  # an ordinary administrator

    def assert_nothing_granted_or_revoked(self):
        self.assertFalse(User.objects.get(pk=self.kim.pk).is_staff)
        self.assertTrue(User.objects.get(pk=self.sam.pk).is_staff)
        self.assertTrue(User.objects.get(pk=self.root.pk).is_superuser)
        self.assertEqual(self.history(self.kim), [])
        self.assertEqual(self.history(self.sam), ['Granted administrator access.'])

    def attempt_to_manage_access(self, client):
        client.post(self.changelist, {'action': GRANT, '_selected_action': [self.kim.pk]})
        client.post(self.changelist, {'action': REVOKE, '_selected_action': [self.sam.pk]})
        client.post(self.changelist, {'action': REVOKE, '_selected_action': [self.root.pk]})

    def test_an_ordinary_administrator_cannot_grant_or_revoke_access(self):
        self.attempt_to_manage_access(self.signed_in_as(self.sam))
        self.assert_nothing_granted_or_revoked()

    def test_an_ordinary_administrator_is_not_offered_the_actions(self):
        html = self.signed_in_as(self.sam).get(self.changelist).content.decode()
        self.assertNotIn('Grant administrator access', html)
        self.assertNotIn('Revoke administrator access', html)
        self.assertIn('Deactivate selected accounts', html)

    def test_a_super_administrator_is_offered_the_actions(self):
        html = self.client.get(self.changelist).content.decode()
        self.assertIn('Grant administrator access', html)
        self.assertIn('Revoke administrator access', html)

    def test_staff_with_every_account_permission_still_cannot_manage_access(self):
        staff = self.staff_with_permissions()
        self.attempt_to_manage_access(self.signed_in_as(staff))
        self.assert_nothing_granted_or_revoked()

    def test_staff_with_no_permissions_cannot_manage_access(self):
        self.attempt_to_manage_access(self.signed_in_as(make_user('nopower@nyu.edu', is_staff=True)))
        self.assert_nothing_granted_or_revoked()

    def test_a_student_cannot_manage_access_or_see_the_admin(self):
        client = self.signed_in_as(self.lee)
        self.attempt_to_manage_access(client)
        client.post(self.changelist, {'action': GRANT, '_selected_action': [self.lee.pk]})
        self.assertFalse(User.objects.get(pk=self.lee.pk).is_staff)
        self.assert_nothing_granted_or_revoked()
        for url in (reverse('admin:index'), self.changelist, self.change_url(self.sam)):
            response = client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/admin/login/', response['Location'])

    def test_signed_out_visitors_cannot_manage_access_or_see_the_admin(self):
        client = Client()
        self.attempt_to_manage_access(client)
        self.assert_nothing_granted_or_revoked()
        for url in (reverse('admin:index'), self.changelist):
            response = client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/admin/login/', response['Location'])

    def test_an_administrator_cannot_make_themselves_a_super_administrator(self):
        client = self.signed_in_as(self.sam)
        client.post(self.change_url(self.sam), {
            'email': 'sam@nyu.edu', 'first_name': 'Sam', 'last_name': 'Lee', 'bio': '', 'is_active': 'on',
            'is_superuser': 'on', 'is_staff': 'on',
        })
        sam = User.objects.get(pk=self.sam.pk)
        self.assertFalse(sam.is_superuser)

    def test_an_administrator_cannot_reach_another_administrators_account(self):
        self.make_administrator(self.lee)
        client = self.signed_in_as(self.sam)
        for target in (self.lee, self.root):
            response = client.post(self.change_url(target), {
                'email': 'x@nyu.edu', 'first_name': 'X', 'last_name': '', 'bio': '', 'is_active': '',
            })
            self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(pk=self.lee.pk).email, 'lee@nyu.edu')
        self.assertEqual(User.objects.get(pk=self.root.pk).email, 'root@nyu.edu')

    def test_an_administrator_cannot_deactivate_or_delete_other_administrators(self):
        self.make_administrator(self.lee)
        client = self.signed_in_as(self.sam)
        client.post(self.changelist, {'action': 'deactivate_accounts', '_selected_action': [self.lee.pk, self.root.pk]})
        client.post(self.changelist, {'action': 'delete_selected', '_selected_action': [self.lee.pk, self.root.pk], 'post': 'yes'})
        self.assertTrue(User.objects.get(pk=self.lee.pk).is_active)
        self.assertTrue(User.objects.get(pk=self.root.pk).is_active)

    def test_an_administrator_cannot_edit_the_groups_that_decide_access(self):
        client = self.signed_in_as(self.sam)
        self.assertEqual(client.get('/admin/auth/group/').status_code, 403)
        self.assertEqual(client.get('/admin/auth/group/add/').status_code, 403)
        group = Group.objects.get(name=ADMIN_GROUP_NAME)
        self.assertEqual(client.post(f'/admin/auth/group/{group.pk}/change/', {'name': 'Hacked'}).status_code, 403)
        self.assertEqual(Group.objects.get(pk=group.pk).name, ADMIN_GROUP_NAME)

    def test_only_an_active_super_administrator_counts_as_authorized(self):
        self.assertTrue(can_manage_administrators(self.root))
        self.assertFalse(can_manage_administrators(User.objects.get(pk=self.sam.pk)))
        self.assertFalse(can_manage_administrators(self.kim))
        self.root.is_active = False
        self.assertFalse(can_manage_administrators(self.root))


class AdminSignInTests(AdministratorAccessTestCase):
    """Access through the real sign-in page, not just a forced login."""

    login_url = '/admin/login/'

    def sign_in(self, email):
        client = Client()
        response = client.post(self.login_url, {'username': email, 'password': PASSWORD, 'next': '/admin/'})
        return client, response

    def test_a_student_cannot_sign_in_to_the_admin(self):
        client, response = self.sign_in('kim@nyu.edu')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter the correct')
        self.assertEqual(client.get(self.changelist).status_code, 302)

    def test_a_granted_administrator_can_sign_in_with_their_email(self):
        self.make_administrator(self.sam)
        client, response = self.sign_in('sam@nyu.edu')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/admin/')
        self.assertEqual(client.get(self.changelist).status_code, 200)

    def test_an_administrator_whose_access_was_revoked_can_no_longer_sign_in(self):
        self.make_administrator(self.sam)
        self.run_action(REVOKE, [self.sam])
        client, response = self.sign_in('sam@nyu.edu')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get(self.changelist).status_code, 302)

    def test_an_ordinary_administrator_is_not_shown_the_groups_that_decide_access(self):
        self.make_administrator(self.sam)
        index = self.signed_in_as(self.sam).get(reverse('admin:index')).content.decode()
        self.assertIn('Users', index)
        self.assertNotIn('Groups', index)
        self.assertIn('Groups', self.client.get(reverse('admin:index')).content.decode())

    def test_deleting_an_administrators_account_removes_them_and_leaves_the_group(self):
        self.make_administrator(self.sam)
        self.client.post(self.delete_url(self.sam), {'post': 'yes'})
        self.assertFalse(User.objects.filter(pk=self.sam.pk).exists())
        self.assertTrue(Group.objects.filter(name=ADMIN_GROUP_NAME).exists())
        self.assertEqual(self.signed_in_as(self.root).get(self.changelist).status_code, 200)


class PersistenceTests(AdministratorAccessTestCase):
    """AC: changes to administrator access remain after refreshing the page."""

    def test_a_grant_is_still_there_on_the_next_visit_and_for_a_new_session(self):
        self.run_action(GRANT, [self.sam])
        self.assertIn('sam@nyu.edu', self.listed(self.role_filter('admin')))
        fresh = Client()
        self.assertTrue(fresh.login(username='sam@nyu.edu', password=PASSWORD))
        self.assertEqual(fresh.get(self.changelist).status_code, 200)

    def test_a_revoke_is_still_there_on_the_next_visit_and_for_a_new_session(self):
        self.run_action(GRANT, [self.sam])
        self.run_action(REVOKE, [self.sam])
        self.assertNotIn('sam@nyu.edu', self.listed(self.role_filter('admin')))
        self.assertIn('sam@nyu.edu', self.listed(self.role_filter('student')))
        fresh = Client()
        self.assertTrue(fresh.login(username='sam@nyu.edu', password=PASSWORD))
        self.assertEqual(fresh.get(self.changelist).status_code, 302)

    def test_the_access_level_is_stored_on_the_account_not_in_the_session(self):
        self.run_action(GRANT, [self.sam])
        stored = User.objects.get(pk=self.sam.pk)
        self.assertEqual((stored.is_staff, stored.is_superuser), (True, False))
        self.assertEqual(self.sam.groups.count(), 1)
