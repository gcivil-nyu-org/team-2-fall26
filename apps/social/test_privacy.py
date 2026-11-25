import json
import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from .models import FoodPost, FriendRequest, SavedPost

# Smallest valid GIF, same fixture apps/api/tests.py uses for uploads.
SMALL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04'
    b'\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
    b'\x02\x4c\x01\x00\x3b'
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FriendVisibilityTests(TestCase):
    """#31: what another student sees about someone who has hidden details."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.viewer = User.objects.create_user(username='viewer@nyu.edu', email='viewer@nyu.edu', password='test123')
        self.sam = User.objects.create_user(
            username='sam@nyu.edu', email='sam@nyu.edu', first_name='Sam', last_name='Lee',
            bio='CS junior', password='test123',
        )
        self.sam.profile_picture.save('sam.gif', SimpleUploadedFile('sam.gif', SMALL_GIF), save=True)
        self.friendship = FriendRequest.objects.create(sender=self.sam, recipient=self.viewer)
        self.friendship.accept()
        self.client.force_login(self.viewer)

    def friend_in_list(self):
        return self.client.get(reverse('social:friends')).json()['friends'][0]

    def hide(self, **fields):
        for name, value in fields.items():
            setattr(self.sam, name, value)
        self.sam.save()

    def test_everything_is_visible_by_default(self):
        friend = self.friend_in_list()
        self.assertEqual(friend['email'], 'sam@nyu.edu')
        self.assertEqual(friend['bio'], 'CS junior')
        self.assertTrue(friend['profile_picture'])

    def test_hidden_email_is_not_sent_to_friends(self):
        self.hide(show_email=False)
        friend = self.friend_in_list()
        self.assertIsNone(friend['email'])
        self.assertEqual(friend['bio'], 'CS junior')
        self.assertNotIn('sam@nyu.edu', self.client.get(reverse('social:friends')).content.decode())

    def test_hidden_bio_is_not_sent_to_friends(self):
        self.hide(show_bio=False)
        friend = self.friend_in_list()
        self.assertEqual(friend['bio'], '')
        self.assertNotIn('CS junior', self.client.get(reverse('social:friends')).content.decode())

    def test_hidden_photo_is_not_sent_to_friends(self):
        self.hide(show_profile_picture=False)
        friend = self.friend_in_list()
        self.assertIsNone(friend['profile_picture'])
        self.assertNotIn('profile-pictures', self.client.get(reverse('social:friends')).content.decode())

    def test_the_name_is_always_visible(self):
        self.hide(show_email=False, show_bio=False, show_profile_picture=False)
        friend = self.friend_in_list()
        self.assertEqual((friend['first_name'], friend['last_name']), ('Sam', 'Lee'))

    def test_friend_profile_page_respects_the_settings(self):
        self.hide(show_email=False, show_bio=False, show_profile_picture=False)
        user = self.client.get(reverse('social:friend_profile', args=[self.friendship.pk])).json()['user']
        self.assertIsNone(user['email'])
        self.assertEqual(user['bio'], '')
        self.assertIsNone(user['profile_picture'])
        self.assertEqual(user['first_name'], 'Sam')

    def test_friend_requests_respect_the_settings_in_both_directions(self):
        stranger = User.objects.create_user(
            username='kim@nyu.edu', email='kim@nyu.edu', first_name='Kim', bio='Hello', password='test123',
            show_email=False, show_bio=False,
        )
        FriendRequest.objects.create(sender=stranger, recipient=self.viewer)
        FriendRequest.objects.create(sender=self.viewer, recipient=User.objects.create_user(
            username='lee@nyu.edu', email='lee@nyu.edu', first_name='Lee', bio='Hi there', password='test123',
            show_email=False, show_bio=False,
        ))
        data = self.client.get(reverse('social:friends')).json()
        for request in data['received_requests'] + data['sent_requests']:
            self.assertIsNone(request['user']['email'])
            self.assertEqual(request['user']['bio'], '')

    def test_conversation_header_respects_the_settings(self):
        self.hide(show_email=False, show_bio=False, show_profile_picture=False)
        friend = self.client.get(reverse('social:conversation', args=[self.sam.pk])).json()['friend']
        self.assertIsNone(friend['email'])
        self.assertEqual(friend['bio'], '')
        self.assertIsNone(friend['profile_picture'])

    def test_message_sender_name_never_falls_back_to_a_hidden_email(self):
        nameless = User.objects.create_user(
            username='nameless@nyu.edu', email='nameless@nyu.edu', password='test123', show_email=False,
        )
        friendship = FriendRequest.objects.create(sender=nameless, recipient=self.viewer)
        friendship.accept()
        # The friend writes first, then the viewer reads the thread.
        self.client.force_login(nameless)
        self.client.post(
            reverse('social:conversation', args=[self.viewer.pk]),
            json.dumps({'body': 'hello'}), content_type='application/json',
        )
        self.client.force_login(self.viewer)
        data = self.client.get(reverse('social:conversation', args=[nameless.pk])).json()
        self.assertEqual(data['messages'][0]['sender_name'], 'SemesterPilot student')
        self.assertNotIn('nameless@nyu.edu', json.dumps(data))

    def test_message_sender_name_uses_a_visible_email_when_there_is_no_name(self):
        nameless = User.objects.create_user(username='nameless@nyu.edu', email='nameless@nyu.edu', password='test123')
        FriendRequest.objects.create(sender=nameless, recipient=self.viewer).accept()
        self.client.force_login(nameless)
        self.client.post(
            reverse('social:conversation', args=[self.viewer.pk]),
            json.dumps({'body': 'hello'}), content_type='application/json',
        )
        self.client.force_login(self.viewer)
        data = self.client.get(reverse('social:conversation', args=[nameless.pk])).json()
        self.assertEqual(data['messages'][0]['sender_name'], 'nameless@nyu.edu')

    def test_friends_list_still_sorts_when_emails_are_hidden(self):
        # Two nameless friends with hidden emails: the sort key must not blow up on None.
        for index in range(2):
            other = User.objects.create_user(
                username=f'n{index}@nyu.edu', email=f'n{index}@nyu.edu', password='test123', show_email=False,
            )
            FriendRequest.objects.create(sender=other, recipient=self.viewer).accept()
        response = self.client.get(reverse('social:friends'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['friends']), 3)

    def test_settings_are_per_student(self):
        other = User.objects.create_user(
            username='kim@nyu.edu', email='kim@nyu.edu', first_name='Kim', bio='Open book', password='test123',
        )
        FriendRequest.objects.create(sender=other, recipient=self.viewer).accept()
        self.hide(show_bio=False)
        by_name = {f['first_name']: f for f in self.client.get(reverse('social:friends')).json()['friends']}
        self.assertEqual(by_name['Sam']['bio'], '')
        self.assertEqual(by_name['Kim']['bio'], 'Open book')


class FriendRequestResponseTests(TestCase):
    """#31: the responses to sending and answering a request follow the settings too."""

    def setUp(self):
        self.alex = User.objects.create_user(username='alex@nyu.edu', email='alex@nyu.edu', password='test123')
        self.kim = User.objects.create_user(
            username='kim@nyu.edu', email='kim@nyu.edu', first_name='Kim', last_name='Park',
            bio='Hello', password='test123', show_email=False, show_bio=False,
        )

    def post(self, body):
        return self.client.post(reverse('social:friend_requests'), json.dumps(body), content_type='application/json')

    def test_sending_a_request_to_someone_hiding_their_details_does_not_echo_them_back(self):
        self.client.force_login(self.alex)
        response = self.post({'email': 'kim@nyu.edu'})
        self.assertEqual(response.status_code, 201)
        user = response.json()['friend_request']['user']
        self.assertEqual(user['first_name'], 'Kim')
        self.assertIsNone(user['email'])
        self.assertEqual(user['bio'], '')

    def test_accepting_a_request_does_not_expose_the_senders_hidden_details(self):
        friend_request = FriendRequest.objects.create(sender=self.kim, recipient=self.alex)
        self.client.force_login(self.alex)
        response = self.client.patch(
            reverse('social:friend_request', args=[friend_request.pk]),
            json.dumps({'status': 'accepted'}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        user = response.json()['friend_request']['user']
        self.assertIsNone(user['email'])
        self.assertEqual(user['bio'], '')

    def test_a_student_still_sees_their_own_details_when_hidden_from_others(self):
        self.client.force_login(self.kim)
        user = self.client.get(reverse('api:profile')).json()['user']
        self.assertEqual(user['email'], 'kim@nyu.edu')
        self.assertEqual(user['bio'], 'Hello')
        self.assertFalse(user['show_email'])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CommunityFeedPrivacyTests(TestCase):
    """#31 with #46: a post's author never exposes details they have hidden."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.author = User.objects.create_user(
            username='sam@nyu.edu', email='sam@nyu.edu', first_name='Sam', last_name='Lee',
            bio='CS junior', password='test123',
        )
        self.author.profile_picture.save('sam.gif', SimpleUploadedFile('sam.gif', SMALL_GIF), save=True)
        self.viewer = User.objects.create_user(username='viewer@nyu.edu', email='viewer@nyu.edu', password='test123')
        self.url = reverse('social:posts')
        FoodPost.objects.create(author=self.author, place_name='Joe\'s Pizza', description='Plain slice.')

    def hide(self, **fields):
        for name, value in fields.items():
            setattr(self.author, name, value)
        self.author.save()

    def feed_author(self):
        self.client.force_login(self.viewer)
        return self.client.get(self.url).json()['posts'][0]['author']

    def test_the_feed_shows_the_authors_email_and_photo_by_default_but_never_the_bio(self):
        author = self.feed_author()
        self.assertEqual(author['email'], 'sam@nyu.edu')
        self.assertTrue(author['profile_picture'])
        self.assertNotIn('bio', author)

    def test_a_hidden_email_is_not_in_the_feed(self):
        self.hide(show_email=False)
        author = self.feed_author()
        self.assertIsNone(author['email'])
        self.client.force_login(self.viewer)
        self.assertNotIn('sam@nyu.edu', self.client.get(self.url).content.decode())

    def test_a_hidden_photo_is_not_in_the_feed(self):
        self.hide(show_profile_picture=False)
        author = self.feed_author()
        self.assertIsNone(author['profile_picture'])
        self.client.force_login(self.viewer)
        self.assertNotIn('profile-pictures', self.client.get(self.url).content.decode())

    def test_hiding_email_and_photo_still_leaves_the_name(self):
        self.hide(show_email=False, show_profile_picture=False)
        author = self.feed_author()
        self.assertEqual((author['first_name'], author['last_name']), ('Sam', 'Lee'))
        self.assertIsNone(author['email'])
        self.assertIsNone(author['profile_picture'])
        self.assertNotIn('bio', author)

    def test_the_bio_never_appears_in_the_feed_whatever_the_setting(self):
        self.client.force_login(self.viewer)
        self.assertNotIn('CS junior', self.client.get(self.url).content.decode())
        self.hide(show_bio=False)
        self.assertNotIn('CS junior', self.client.get(self.url).content.decode())

    def test_creating_a_post_does_not_echo_hidden_details_back(self):
        self.hide(show_email=False, show_profile_picture=False)
        self.client.force_login(self.author)
        response = self.client.post(
            self.url, json.dumps({'place_name': 'Mamoun\'s', 'description': 'Best falafel.'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        author = response.json()['post']['author']
        self.assertEqual(author['first_name'], 'Sam')
        self.assertIsNone(author['email'])
        self.assertIsNone(author['profile_picture'])
        self.assertNotIn('bio', author)
        self.assertNotIn('sam@nyu.edu', response.content.decode())

    def test_one_authors_settings_do_not_change_another_authors_posts(self):
        other = User.objects.create_user(
            username='kim@nyu.edu', email='kim@nyu.edu', first_name='Kim', password='test123',
        )
        FoodPost.objects.create(author=other, place_name='Katz\'s', description='Pastrami.')
        self.hide(show_email=False)
        self.client.force_login(self.viewer)
        by_email = {post['author']['first_name']: post['author']['email'] for post in self.client.get(self.url).json()['posts']}
        self.assertEqual(by_email, {'Sam': None, 'Kim': 'kim@nyu.edu'})

    # #47 and #53 added two more places that show a post's author: a single
    # post's page and the saved list. Hidden details must stay hidden there too.
    def detail_author(self):
        post = FoodPost.objects.get()
        self.client.force_login(self.viewer)
        return self.client.get(reverse('social:post', args=[post.pk])).json()['post']['author']

    def saved_author(self):
        SavedPost.objects.create(user=self.viewer, post=FoodPost.objects.get())
        self.client.force_login(self.viewer)
        return self.client.get(reverse('social:saved_posts')).json()['posts'][0]['author']

    def test_a_single_post_shows_email_and_photo_by_default_but_never_the_bio(self):
        author = self.detail_author()
        self.assertEqual(author['email'], 'sam@nyu.edu')
        self.assertTrue(author['profile_picture'])
        self.assertNotIn('bio', author)

    def test_a_hidden_email_and_photo_are_not_on_the_single_post_page(self):
        self.hide(show_email=False, show_profile_picture=False)
        author = self.detail_author()
        self.assertEqual((author['first_name'], author['last_name']), ('Sam', 'Lee'))
        self.assertIsNone(author['email'])
        self.assertIsNone(author['profile_picture'])
        self.assertNotIn('bio', author)
        post = FoodPost.objects.get()
        body = self.client.get(reverse('social:post', args=[post.pk])).content.decode()
        self.assertNotIn('sam@nyu.edu', body)
        self.assertNotIn('profile-pictures', body)
        self.assertNotIn('CS junior', body)

    def test_the_single_post_page_follows_a_change_of_setting_straight_away(self):
        self.assertEqual(self.detail_author()['email'], 'sam@nyu.edu')
        self.hide(show_email=False)
        self.assertIsNone(self.detail_author()['email'])
        self.hide(show_email=True)
        self.assertEqual(self.detail_author()['email'], 'sam@nyu.edu')

    def test_the_saved_list_shows_email_and_photo_by_default_but_never_the_bio(self):
        author = self.saved_author()
        self.assertEqual(author['email'], 'sam@nyu.edu')
        self.assertTrue(author['profile_picture'])
        self.assertNotIn('bio', author)

    def test_a_hidden_email_and_photo_are_not_in_the_saved_list(self):
        self.hide(show_email=False, show_profile_picture=False)
        author = self.saved_author()
        self.assertEqual(author['first_name'], 'Sam')
        self.assertIsNone(author['email'])
        self.assertIsNone(author['profile_picture'])
        body = self.client.get(reverse('social:saved_posts')).content.decode()
        self.assertNotIn('sam@nyu.edu', body)
        self.assertNotIn('profile-pictures', body)
        self.assertNotIn('CS junior', body)

    def test_saving_or_unsaving_a_post_does_not_reveal_the_author(self):
        self.hide(show_email=False, show_profile_picture=False)
        post = FoodPost.objects.get()
        self.client.force_login(self.viewer)
        saved = self.client.put(reverse('social:post_save', args=[post.pk]))
        unsaved = self.client.delete(reverse('social:post_save', args=[post.pk]))
        for response in (saved, unsaved):
            self.assertNotIn('sam@nyu.edu', response.content.decode())
            self.assertNotIn('profile-pictures', response.content.decode())

    # #122: editing (#121) and sharing (#125) came after #108, so they get the
    # same checks: hidden details stay hidden, the name always shows and the
    # bio never does.
    def edit_response(self, **changes):
        post = FoodPost.objects.get()
        self.client.force_login(self.author)
        return self.client.patch(
            reverse('social:post', args=[post.pk]),
            json.dumps(changes or {'description': 'Get the grandma slice.'}),
            content_type='application/json',
        )

    def test_editing_a_post_shows_email_and_photo_by_default_but_never_the_bio(self):
        response = self.edit_response()
        self.assertEqual(response.status_code, 200)
        author = response.json()['post']['author']
        self.assertEqual(author['email'], 'sam@nyu.edu')
        self.assertTrue(author['profile_picture'])
        self.assertNotIn('bio', author)

    def test_editing_a_post_does_not_echo_hidden_details_back(self):
        # Same as creating a post: the author's own response follows their
        # settings too.
        self.hide(show_email=False, show_profile_picture=False)
        response = self.edit_response()
        self.assertEqual(response.status_code, 200)
        author = response.json()['post']['author']
        self.assertEqual((author['first_name'], author['last_name']), ('Sam', 'Lee'))
        self.assertIsNone(author['email'])
        self.assertIsNone(author['profile_picture'])
        self.assertNotIn('bio', author)
        body = response.content.decode()
        self.assertNotIn('sam@nyu.edu', body)
        self.assertNotIn('profile-pictures', body)
        self.assertNotIn('CS junior', body)

    def test_each_setting_applies_on_its_own_in_the_edit_response(self):
        for hidden, expected_email, photo_shown in [
            ({'show_email': False, 'show_profile_picture': True}, None, True),
            ({'show_email': True, 'show_profile_picture': False}, 'sam@nyu.edu', False),
        ]:
            with self.subTest(**hidden):
                self.hide(**hidden)
                author = self.edit_response().json()['post']['author']
                self.assertEqual(author['email'], expected_email)
                self.assertEqual(bool(author['profile_picture']), photo_shown)

    def test_an_edit_shows_on_the_post_page_with_the_authors_settings_applied(self):
        self.hide(show_email=False, show_profile_picture=False)
        self.edit_response(description='Now with a grandma slice.')
        post = FoodPost.objects.get()
        self.client.force_login(self.viewer)
        shown = self.client.get(reverse('social:post', args=[post.pk])).json()['post']
        self.assertEqual(shown['description'], 'Now with a grandma slice.')
        self.assertEqual(shown['author']['first_name'], 'Sam')
        self.assertIsNone(shown['author']['email'])
        self.assertIsNone(shown['author']['profile_picture'])

    def test_a_refused_edit_reveals_nothing_about_the_author(self):
        post = FoodPost.objects.get()
        self.client.force_login(self.viewer)
        response = self.client.patch(
            reverse('social:post', args=[post.pk]), json.dumps({'description': 'Hacked.'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        body = response.content.decode()
        for detail in ('sam@nyu.edu', 'profile-pictures', 'CS junior', 'Sam'):
            self.assertNotIn(detail, body)

    def test_a_shared_post_follows_the_authors_settings_in_the_conversation(self):
        # Kim shares Sam's post with the viewer (#125). Both of them see the
        # post's author the way Sam's settings allow.
        kim = User.objects.create_user(username='kim@nyu.edu', email='kim@nyu.edu', first_name='Kim', password='test123')
        FriendRequest.objects.create(sender=kim, recipient=self.viewer).accept()
        post = FoodPost.objects.get()
        self.client.force_login(kim)
        shared = self.client.post(
            reverse('social:post_share', args=[post.pk]), json.dumps({'friend_id': self.viewer.pk}),
            content_type='application/json',
        )
        self.assertEqual(shared.status_code, 201)

        def shared_author(viewer, friend):
            self.client.force_login(viewer)
            [message] = self.client.get(reverse('social:conversation', args=[friend.pk])).json()['messages']
            return message['shared_post']['author']

        author = shared_author(self.viewer, kim)
        self.assertEqual(author['email'], 'sam@nyu.edu')
        self.assertTrue(author['profile_picture'])

        self.hide(show_email=False, show_profile_picture=False)
        for viewer, friend in ((self.viewer, kim), (kim, self.viewer)):
            with self.subTest(viewer=viewer.email):
                author = shared_author(viewer, friend)
                self.assertEqual(author['first_name'], 'Sam')
                self.assertIsNone(author['email'])
                self.assertIsNone(author['profile_picture'])
                self.assertNotIn('bio', author)
                body = self.client.get(reverse('social:conversation', args=[friend.pk])).content.decode()
                self.assertNotIn('sam@nyu.edu', body)
                self.assertNotIn('profile-pictures', body)
                self.assertNotIn('CS junior', body)
