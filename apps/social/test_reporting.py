import json

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.administrators import ADMIN_GROUP_NAME, grant_administrator_access
from apps.accounts.models import User

from .models import ContentReport, FoodPost, PostComment

PASSWORD = 'report-test-password-2026'


def make_user(email, **fields):
    return User.objects.create_user(username=email, email=email, password=PASSWORD, **fields)


class ReportTestCase(TestCase):
    def setUp(self):
        self.alex = make_user('alex@nyu.edu', first_name='Alex')
        self.sam = make_user('sam@nyu.edu', first_name='Sam', last_name='Lee')
        self.jordan = make_user('jordan@nyu.edu', first_name='Jordan')
        self.post = FoodPost.objects.create(author=self.sam, place_name="Joe's Pizza", description='Classic slice.')
        self.comment = PostComment.objects.create(post=self.post, author=self.jordan, body='Buy my crypto course!')
        self.client.force_login(self.alex)

    def report_post(self, data, pk=None):
        url = reverse('social:post_report', args=[pk or self.post.pk])
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def report_comment(self, data, pk=None):
        url = reverse('social:comment_report', args=[pk or self.comment.pk])
        return self.client.post(url, json.dumps(data), content_type='application/json')


class ReportSubmissionTests(ReportTestCase):
    # #67: reporting a post or comment.
    def test_reporting_a_post_stores_the_report_and_confirms_it(self):
        response = self.report_post({'reason': 'spam', 'details': '  Same post three times  '})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'reported': True})
        report = ContentReport.objects.get()
        self.assertEqual((report.reporter, report.post, report.comment), (self.alex, self.post, None))
        self.assertEqual((report.reason, report.details), ('spam', 'Same post three times'))

    def test_reporting_a_comment_stores_the_report_and_confirms_it(self):
        response = self.report_comment({'reason': 'other'})
        self.assertEqual(response.status_code, 201)
        report = ContentReport.objects.get()
        self.assertEqual((report.reporter, report.post, report.comment), (self.alex, None, self.comment))
        self.assertEqual((report.reason, report.details), ('other', ''))

    def test_every_listed_reason_is_accepted(self):
        for reason in ContentReport.Reason.values:
            with self.subTest(reason=reason):
                ContentReport.objects.all().delete()
                self.assertEqual(self.report_post({'reason': reason}).status_code, 201)

    def test_reporting_does_not_hide_or_change_the_content(self):
        self.report_post({'reason': 'inappropriate'})
        self.report_comment({'reason': 'spam'})
        for viewer in (self.alex, self.jordan):
            with self.subTest(viewer=viewer.email):
                self.client.force_login(viewer)
                feed = self.client.get(reverse('social:posts')).json()['posts']
                self.assertEqual([post['id'] for post in feed], [self.post.pk])
                self.assertEqual(feed[0]['comment_count'], 1)
                detail = self.client.get(reverse('social:post', args=[self.post.pk]))
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()['post']['description'], 'Classic slice.')
                comments = self.client.get(reverse('social:post_comments', args=[self.post.pk])).json()['comments']
                self.assertEqual([c['body'] for c in comments], ['Buy my crypto course!'])
        self.assertTrue(FoodPost.objects.filter(pk=self.post.pk).exists())
        self.assertTrue(PostComment.objects.filter(pk=self.comment.pk).exists())


class DuplicateReportTests(ReportTestCase):
    def test_a_post_can_only_be_reported_once_per_student(self):
        self.report_post({'reason': 'spam'})
        response = self.report_post({'reason': 'other'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], 'You’ve already reported this.')
        self.assertEqual(ContentReport.objects.get().reason, 'spam')

    def test_a_comment_can_only_be_reported_once_per_student(self):
        self.report_comment({'reason': 'spam'})
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 409)
        self.assertEqual(ContentReport.objects.count(), 1)

    def test_other_students_and_other_content_can_still_be_reported(self):
        self.report_post({'reason': 'spam'})
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 201)
        other_post = FoodPost.objects.create(author=self.sam, place_name='Mamoun’s', description='Falafel.')
        self.assertEqual(self.report_post({'reason': 'spam'}, pk=other_post.pk).status_code, 201)
        self.client.force_login(self.jordan)
        self.assertEqual(self.report_post({'reason': 'spam'}).status_code, 201)
        self.assertEqual(ContentReport.objects.count(), 4)

    def test_the_database_keeps_one_report_per_student_per_item(self):
        ContentReport.objects.create(reporter=self.alex, post=self.post, reason='spam')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReport.objects.create(reporter=self.alex, post=self.post, reason='other')
        ContentReport.objects.create(reporter=self.alex, comment=self.comment, reason='spam')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReport.objects.create(reporter=self.alex, comment=self.comment, reason='other')

    def test_a_report_is_about_exactly_one_post_or_comment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReport.objects.create(reporter=self.alex, reason='spam')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentReport.objects.create(reporter=self.alex, post=self.post, comment=self.comment, reason='spam')


class ReportedStatusTests(ReportTestCase):
    def test_posts_show_whether_you_reported_them(self):
        self.report_post({'reason': 'spam'})
        self.assertTrue(self.client.get(reverse('social:posts')).json()['posts'][0]['is_reported'])
        self.assertTrue(self.client.get(reverse('social:post', args=[self.post.pk])).json()['post']['is_reported'])
        self.client.force_login(self.jordan)
        self.assertFalse(self.client.get(reverse('social:posts')).json()['posts'][0]['is_reported'])

    def test_comments_show_whether_you_reported_them_and_whether_they_are_yours(self):
        self.report_comment({'reason': 'spam'})
        [comment] = self.client.get(reverse('social:post_comments', args=[self.post.pk])).json()['comments']
        self.assertTrue(comment['is_reported'])
        self.assertFalse(comment['is_author'])
        self.client.force_login(self.jordan)
        [comment] = self.client.get(reverse('social:post_comments', args=[self.post.pk])).json()['comments']
        self.assertFalse(comment['is_reported'])
        self.assertTrue(comment['is_author'])

    def test_a_new_comment_is_yours_and_not_reported(self):
        response = self.client.post(
            reverse('social:post_comments', args=[self.post.pk]), json.dumps({'body': 'Nice'}),
            content_type='application/json',
        )
        comment = response.json()['comment']
        self.assertTrue(comment['is_author'])
        self.assertFalse(comment['is_reported'])


class ReportRulesTests(ReportTestCase):
    def test_you_cannot_report_your_own_post_or_comment(self):
        self.client.force_login(self.sam)
        self.assertEqual(self.report_post({'reason': 'spam'}).status_code, 400)
        self.client.force_login(self.jordan)
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 400)
        self.assertEqual(ContentReport.objects.count(), 0)

    def test_missing_or_hidden_content_cannot_be_reported(self):
        self.assertEqual(self.report_post({'reason': 'spam'}, pk=999999).status_code, 404)
        self.assertEqual(self.report_comment({'reason': 'spam'}, pk=999999).status_code, 404)
        self.jordan.is_active = False
        self.jordan.save()
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 404)
        self.jordan.is_active = True
        self.jordan.save()
        self.sam.is_active = False
        self.sam.save()
        self.assertEqual(self.report_post({'reason': 'spam'}).status_code, 404)
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 404)
        self.assertEqual(ContentReport.objects.count(), 0)

    def test_rejects_a_missing_or_unknown_reason_and_bad_details(self):
        cases = [
            ({}, 'reason'),
            ({'reason': ''}, 'reason'),
            ({'reason': 'boring'}, 'reason'),
            ({'reason': 'spam', 'details': 123}, 'details'),
            ({'reason': 'spam', 'details': 'x' * 501}, 'details'),
        ]
        for data, field in cases:
            with self.subTest(data=str(data)[:40]):
                response = self.report_post(data)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()['errors'])
        self.assertEqual(ContentReport.objects.count(), 0)

    def test_rejects_malformed_json(self):
        url = reverse('social:post_report', args=[self.post.pk])
        self.assertEqual(self.client.post(url, '{', content_type='application/json').status_code, 400)
        self.assertEqual(self.report_post([]).status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.report_post({'reason': 'spam'}).status_code, 401)
        self.assertEqual(self.report_comment({'reason': 'spam'}).status_code, 401)
        self.assertEqual(ContentReport.objects.count(), 0)

    def test_only_post_is_allowed(self):
        for url in (
            reverse('social:post_report', args=[self.post.pk]),
            reverse('social:comment_report', args=[self.comment.pk]),
        ):
            for method in (self.client.get, self.client.put, self.client.delete):
                with self.subTest(url=url, method=method.__name__):
                    self.assertEqual(method(url).status_code, 405)

    def test_reports_go_away_with_the_content(self):
        self.report_post({'reason': 'spam'})
        self.report_comment({'reason': 'spam'})
        self.comment.delete()
        self.assertEqual(list(ContentReport.objects.values_list('post', flat=True)), [self.post.pk])
        self.post.delete()
        self.assertEqual(ContentReport.objects.count(), 0)


# Admin pages link to Django's admin CSS; see apps/accounts/test_admin.py.
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ReportQueueTests(ReportTestCase):
    # #67: submitted reports show up in the administrators' review queue.
    def setUp(self):
        super().setUp()
        self.report_post({'reason': 'inappropriate', 'details': 'Rude description'})
        self.report_comment({'reason': 'spam'})
        self.changelist = reverse('admin:social_contentreport_changelist')

    def test_a_super_administrator_sees_reports_with_the_content_and_reason(self):
        root = User.objects.create_superuser(username='root@nyu.edu', email='root@nyu.edu', password=PASSWORD)
        self.client.force_login(root)
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Joe&#x27;s Pizza')
        self.assertContains(response, 'Buy my crypto course!')
        self.assertContains(response, 'Inappropriate content')
        self.assertContains(response, 'Spam')
        self.assertContains(response, 'alex@nyu.edu')
        self.assertContains(response, f'/app/community/posts/{self.post.pk}')

    def test_an_administrator_can_open_the_queue_and_a_report(self):
        admin = make_user('admin@nyu.edu')
        grant_administrator_access(admin)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.changelist).status_code, 200)
        report = ContentReport.objects.get(post=self.post)
        response = self.client.get(reverse('admin:social_contentreport_change', args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rude description')

    def test_the_administrators_group_includes_viewing_reports(self):
        admin = make_user('admin@nyu.edu')
        grant_administrator_access(admin)
        group = Group.objects.get(name=ADMIN_GROUP_NAME)
        self.assertTrue(group.permissions.filter(codename='view_contentreport').exists())
        self.assertTrue(User.objects.get(pk=admin.pk).has_perm('social.view_contentreport'))

    def test_students_cannot_see_the_queue(self):
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])

    def test_reports_cannot_be_added_changed_or_deleted_from_the_queue(self):
        root = User.objects.create_superuser(username='root@nyu.edu', email='root@nyu.edu', password=PASSWORD)
        self.client.force_login(root)
        report = ContentReport.objects.get(post=self.post)
        self.assertEqual(self.client.get(reverse('admin:social_contentreport_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:social_contentreport_delete', args=[report.pk])).status_code, 403)
        self.client.post(reverse('admin:social_contentreport_change', args=[report.pk]), {'reason': 'other'})
        self.assertEqual(ContentReport.objects.get(pk=report.pk).reason, 'inappropriate')
