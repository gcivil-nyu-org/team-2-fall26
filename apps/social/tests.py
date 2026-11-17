import json
import shutil
import tempfile
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

from .models import FoodPost, FriendRequest

# A 1x1 GIF — just enough bytes to be a valid image for ImageField to accept.
SMALL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04'
    b'\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
    b'\x02\x4c\x01\x00\x3b'
)


class SocialTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alex@nyu.edu', email='alex@nyu.edu', password='friend-test-password')
        self.other = User.objects.create_user(username='sam@nyu.edu', email='sam@nyu.edu', password='friend-test-password', first_name='Sam', last_name='Lee')
        self.third = User.objects.create_user(username='jordan@nyu.edu', email='jordan@nyu.edu', password='friend-test-password', first_name='Jordan')
        self.client.force_login(self.user)


class SendFriendRequestTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('social:friend_requests')

    def send(self, email):
        return self.client.post(self.url, json.dumps({'email': email}), content_type='application/json')

    def test_requires_authentication(self):
        self.client.logout()
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 401)

    def test_sends_a_pending_request_by_email(self):
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 201)
        payload = response.json()['friend_request']
        self.assertEqual(payload['status'], 'pending')
        self.assertEqual(payload['direction'], 'sent')
        self.assertEqual(payload['user']['email'], self.other.email)
        self.assertEqual(FriendRequest.objects.count(), 1)
        request = FriendRequest.objects.get()
        self.assertEqual(request.sender, self.user)
        self.assertEqual(request.recipient, self.other)
        self.assertEqual(request.status, FriendRequest.Status.PENDING)

    def test_email_match_is_case_insensitive(self):
        response = self.send(self.other.email.upper())
        self.assertEqual(response.status_code, 201)

    def test_email_is_required(self):
        response = self.send('')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])

    def test_malformed_email_is_rejected(self):
        response = self.send('not-an-email')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])

    def test_surrounding_whitespace_in_the_email_is_trimmed(self):
        response = self.send(f'  {self.other.email}  ')
        self.assertEqual(response.status_code, 201)

    def test_rejects_invalid_json(self):
        response = self.client.post(self.url, 'not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_cannot_send_a_request_to_self(self):
        response = self.send(self.user.email)
        self.assertEqual(response.status_code, 400)
        self.assertIn('yourself', response.json()['errors']['email'][0])
        self.assertEqual(FriendRequest.objects.count(), 0)

    def test_unknown_email_is_rejected(self):
        response = self.send('nobody@nyu.edu')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['errors'])
        self.assertEqual(FriendRequest.objects.count(), 0)

    def test_duplicate_pending_request_in_the_same_direction_is_rejected(self):
        self.send(self.other.email)
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 400)
        self.assertIn('already sent', response.json()['errors']['email'][0])
        self.assertEqual(FriendRequest.objects.count(), 1)

    def test_a_pending_request_from_the_other_person_is_accepted_instead_of_duplicated(self):
        FriendRequest.objects.create(sender=self.other, recipient=self.user)
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 200)
        payload = response.json()['friend_request']
        self.assertEqual(payload['status'], 'accepted')
        self.assertEqual(FriendRequest.objects.count(), 1)
        request = FriendRequest.objects.get()
        self.assertEqual(request.status, FriendRequest.Status.ACCEPTED)
        self.assertIsNotNone(request.responded_at)
        # The original request keeps its original sender/recipient — only its
        # status changed, nothing was recreated in the other direction.
        self.assertEqual(request.sender, self.other)
        self.assertEqual(request.recipient, self.user)

    def test_cannot_send_a_request_to_an_existing_friend(self):
        request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        request.accept()
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 400)
        self.assertIn('already friends', response.json()['errors']['email'][0])
        self.assertEqual(FriendRequest.objects.count(), 1)

    def test_a_declined_request_does_not_block_sending_a_new_one(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        declined.decline()
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FriendRequest.objects.count(), 2)

    def test_a_declined_request_from_the_other_person_can_be_sent_again_by_them(self):
        declined = FriendRequest.objects.create(sender=self.other, recipient=self.user)
        declined.decline()
        response = self.send(self.other.email)
        self.assertEqual(response.status_code, 201)
        new_request = FriendRequest.objects.exclude(pk=declined.pk).get()
        self.assertEqual(new_request.sender, self.user)
        self.assertEqual(new_request.status, FriendRequest.Status.PENDING)

    def test_database_rejects_a_duplicate_pending_request_outside_the_view(self):
        FriendRequest.objects.create(sender=self.user, recipient=self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FriendRequest.objects.create(sender=self.user, recipient=self.other)

    def test_database_rejects_a_self_request_outside_the_view(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            FriendRequest.objects.create(sender=self.user, recipient=self.user)


class FriendRequestModelTests(SocialTestCase):
    def test_other_returns_whichever_side_of_the_pair_is_not_the_viewer(self):
        friend_request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        self.assertEqual(friend_request.other(self.user), self.other)
        self.assertEqual(friend_request.other(self.other), self.user)

    def test_accept_sets_status_and_responded_at(self):
        friend_request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        self.assertIsNone(friend_request.responded_at)
        friend_request.accept()
        self.assertEqual(friend_request.status, FriendRequest.Status.ACCEPTED)
        self.assertIsNotNone(friend_request.responded_at)

    def test_decline_sets_status_and_responded_at(self):
        friend_request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        friend_request.decline()
        self.assertEqual(friend_request.status, FriendRequest.Status.DECLINED)
        self.assertIsNotNone(friend_request.responded_at)

    def test_between_finds_a_request_regardless_of_which_side_initiated_it(self):
        friend_request = FriendRequest.objects.create(sender=self.other, recipient=self.user)
        self.assertEqual(list(FriendRequest.objects.between(self.user, self.other)), [friend_request])
        self.assertEqual(list(FriendRequest.objects.between(self.other, self.user)), [friend_request])
        self.assertEqual(list(FriendRequest.objects.between(self.user, self.third)), [])

    def test_str_includes_both_sides_and_status(self):
        friend_request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        text = str(friend_request)
        self.assertIn(str(self.user), text)
        self.assertIn(str(self.other), text)
        self.assertIn('pending', text)

    def test_full_clean_rejects_a_self_request_with_a_validation_error(self):
        # The view and the database constraint both already stop this, but a
        # ModelForm (the Django admin, chiefly) calls full_clean() rather than
        # relying on the database, so clean() needs to catch it too.
        friend_request = FriendRequest(sender=self.user, recipient=self.user)
        with self.assertRaises(ValidationError):
            friend_request.full_clean()

    def test_full_clean_rejects_a_new_request_between_existing_friends(self):
        existing = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        existing.accept()
        duplicate = FriendRequest(sender=self.other, recipient=self.user)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_full_clean_allows_a_new_request_after_a_decline(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        declined.decline()
        new_request = FriendRequest(sender=self.user, recipient=self.other)
        new_request.full_clean()  # should not raise

    def test_full_clean_does_not_flag_a_request_against_itself_as_a_duplicate(self):
        # Re-validating an already-accepted request (e.g. re-saving it in the
        # admin) must not trip the "already friends" check against itself.
        friend_request = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        friend_request.accept()
        friend_request.full_clean()  # should not raise


class FriendsListTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('social:friends')

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_empty_state(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'friends': [], 'received_requests': [], 'sent_requests': []})

    def test_lists_sent_and_received_pending_requests_separately(self):
        FriendRequest.objects.create(sender=self.user, recipient=self.other)
        FriendRequest.objects.create(sender=self.third, recipient=self.user)
        data = self.client.get(self.url).json()
        self.assertEqual(len(data['sent_requests']), 1)
        self.assertEqual(data['sent_requests'][0]['user']['email'], self.other.email)
        self.assertEqual(data['sent_requests'][0]['direction'], 'sent')
        self.assertEqual(len(data['received_requests']), 1)
        self.assertEqual(data['received_requests'][0]['user']['email'], self.third.email)
        self.assertEqual(data['received_requests'][0]['direction'], 'received')

    def test_lists_accepted_friends_regardless_of_who_sent_the_request(self):
        sent_by_me = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        sent_by_me.accept()
        sent_to_me = FriendRequest.objects.create(sender=self.third, recipient=self.user)
        sent_to_me.accept()
        data = self.client.get(self.url).json()
        emails = {friend['email'] for friend in data['friends']}
        self.assertEqual(emails, {self.other.email, self.third.email})
        self.assertEqual(data['sent_requests'], [])
        self.assertEqual(data['received_requests'], [])

    def test_each_friend_carries_the_friendship_id_needed_to_remove_them(self):
        # The friend object's own 'id' is the OTHER user's id, not this
        # FriendRequest row's id — removing a friend needs the latter.
        friendship = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        friendship.accept()
        data = self.client.get(self.url).json()
        self.assertEqual(data['friends'][0]['friendship_id'], friendship.pk)
        self.assertEqual(data['friends'][0]['id'], self.other.pk)

    def test_declined_requests_are_not_listed_anywhere(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        declined.decline()
        data = self.client.get(self.url).json()
        self.assertEqual(data, {'friends': [], 'received_requests': [], 'sent_requests': []})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FriendsListProfilePictureTests(SocialTestCase):
    # #17/#18 AC: a friend request (and a friend) should show the other
    # person's profile photo. _user_summary() just passes through whatever
    # apps.accounts.models.User.profile_picture already has, same as
    # apps/api/views.py's own _user_payload does for a user's own profile.
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.url = reverse('social:friends')
        self.other.profile_picture = SimpleUploadedFile('avatar.gif', SMALL_GIF, content_type='image/gif')
        self.other.save()

    def test_a_friends_profile_picture_url_is_included(self):
        accepted = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        accepted.accept()
        data = self.client.get(self.url).json()
        friend = next(item for item in data['friends'] if item['email'] == self.other.email)
        self.assertIsNotNone(friend['profile_picture'])
        self.assertIn('avatar', friend['profile_picture'])

    def test_a_friend_with_no_profile_picture_reports_null_not_an_error(self):
        accepted = FriendRequest.objects.create(sender=self.user, recipient=self.third)
        accepted.accept()
        data = self.client.get(self.url).json()
        friend = next(item for item in data['friends'] if item['email'] == self.third.email)
        self.assertIsNone(friend['profile_picture'])

    def test_a_received_requests_sender_profile_picture_is_included(self):
        FriendRequest.objects.create(sender=self.other, recipient=self.user)
        data = self.client.get(self.url).json()
        self.assertIsNotNone(data['received_requests'][0]['user']['profile_picture'])

    def test_a_sent_requests_recipient_profile_picture_is_included(self):
        FriendRequest.objects.create(sender=self.user, recipient=self.other)
        data = self.client.get(self.url).json()
        self.assertIsNotNone(data['sent_requests'][0]['user']['profile_picture'])


class RemoveFriendTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.friendship = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        self.friendship.accept()
        self.url = reverse('social:friend_request', args=[self.friendship.pk])

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.delete(self.url).status_code, 401)

    def test_the_user_who_sent_the_original_request_can_remove_the_friendship(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FriendRequest.objects.filter(pk=self.friendship.pk).exists())

    def test_the_user_who_received_the_original_request_can_also_remove_the_friendship(self):
        # Removing a friend isn't directional — it shouldn't matter who sent
        # the original request. (AC: "I can remove a student who is
        # currently in my friends list.")
        self.client.force_login(self.other)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FriendRequest.objects.filter(pk=self.friendship.pk).exists())

    def test_a_stranger_cannot_remove_a_friendship_they_are_not_part_of(self):
        self.client.force_login(self.third)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FriendRequest.objects.filter(pk=self.friendship.pk).exists())

    def test_removed_friend_disappears_from_both_sides_friends_list(self):
        # AC: "After removal, the student no longer appears in my friends
        # list" — checked from both ends, since it's a shared relationship.
        self.client.delete(self.url)
        mine = self.client.get(reverse('social:friends')).json()
        self.assertEqual(mine['friends'], [])
        self.client.force_login(self.other)
        theirs = self.client.get(reverse('social:friends')).json()
        self.assertEqual(theirs['friends'], [])

    def test_removing_a_friend_does_not_delete_either_account(self):
        # AC: "Removing a friend does not delete either student's account or
        # previous messages." This app has no message model at all (nothing
        # to lose there), so the account-preservation half is what a test
        # can actually exercise: removing the friendship must never touch
        # the User rows themselves.
        self.client.delete(self.url)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())

    def test_removing_a_friend_allows_sending_a_new_request_afterward(self):
        self.client.delete(self.url)
        response = self.client.post(
            reverse('social:friend_requests'),
            json.dumps({'email': self.other.email}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

    def test_cannot_remove_a_declined_request_this_way(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.third)
        declined.decline()
        response = self.client.delete(reverse('social:friend_request', args=[declined.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(FriendRequest.objects.filter(pk=declined.pk).exists())

    def test_unknown_friendship_id_is_a_404(self):
        response = self.client.delete(reverse('social:friend_request', args=[999999]))
        self.assertEqual(response.status_code, 404)


class FriendProfileTests(SocialTestCase):
    # #18 AC: "I can select a friend from the list to view their profile."
    def setUp(self):
        super().setUp()
        self.friendship = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        self.friendship.accept()
        self.url = reverse('social:friend_profile', args=[self.friendship.pk])

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_the_friends_profile(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        user = response.json()['user']
        self.assertEqual(user['email'], self.other.email)
        self.assertEqual(user['first_name'], self.other.first_name)

    def test_either_side_of_the_friendship_can_view_the_others_profile(self):
        self.client.force_login(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], self.user.email)

    def test_a_stranger_cannot_view_a_friendship_they_are_not_part_of(self):
        self.client.force_login(self.third)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_a_pending_requests_sender_is_not_accessible_as_a_friend_profile(self):
        # Only an accepted friendship counts — sending or receiving a request
        # doesn't give either side a "profile" view of the other yet.
        pending = FriendRequest.objects.create(sender=self.user, recipient=self.third)
        response = self.client.get(reverse('social:friend_profile', args=[pending.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_declined_requests_other_party_is_not_accessible(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.third)
        declined.decline()
        response = self.client.get(reverse('social:friend_profile', args=[declined.pk]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_friendship_id_is_a_404(self):
        response = self.client.get(reverse('social:friend_profile', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_removed_friendship_is_no_longer_accessible(self):
        self.client.delete(reverse('social:friend_request', args=[self.friendship.pk]))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


class RespondToFriendRequestTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.incoming = FriendRequest.objects.create(sender=self.other, recipient=self.user)
        self.url = reverse('social:friend_request', args=[self.incoming.pk])

    def patch(self, status):
        return self.client.patch(self.url, json.dumps({'status': status}), content_type='application/json')

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.patch('accepted').status_code, 401)

    def test_recipient_can_accept(self):
        response = self.patch('accepted')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['friend_request']['status'], 'accepted')
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.status, FriendRequest.Status.ACCEPTED)
        self.assertIsNotNone(self.incoming.responded_at)

    def test_recipient_can_decline(self):
        response = self.patch('declined')
        self.assertEqual(response.status_code, 200)
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.status, FriendRequest.Status.DECLINED)

    def test_sender_cannot_respond_to_their_own_request(self):
        self.client.force_login(self.other)
        response = self.patch('accepted')
        self.assertEqual(response.status_code, 403)
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.status, FriendRequest.Status.PENDING)

    def test_a_stranger_gets_a_404_not_a_403(self):
        # Keeps the request's existence private from anyone who isn't a party
        # to it, consistent with how courses/assignments are looked up elsewhere.
        self.client.force_login(self.third)
        response = self.patch('accepted')
        self.assertEqual(response.status_code, 404)

    def test_invalid_status_value_is_rejected(self):
        response = self.patch('maybe')
        self.assertEqual(response.status_code, 400)
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.status, FriendRequest.Status.PENDING)

    def test_cannot_respond_twice(self):
        self.patch('accepted')
        response = self.patch('declined')
        self.assertEqual(response.status_code, 400)
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.status, FriendRequest.Status.ACCEPTED)

    def test_rejects_invalid_json(self):
        response = self.client.patch(self.url, 'not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)


class CancelFriendRequestTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.outgoing = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        self.url = reverse('social:friend_request', args=[self.outgoing.pk])

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.delete(self.url).status_code, 401)

    def test_sender_can_cancel_a_pending_request(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FriendRequest.objects.filter(pk=self.outgoing.pk).exists())

    def test_recipient_cannot_cancel_a_request_sent_to_them(self):
        self.client.force_login(self.other)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(FriendRequest.objects.filter(pk=self.outgoing.pk).exists())

    def test_a_stranger_gets_a_404(self):
        self.client.force_login(self.third)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 404)

    # Deleting an ACCEPTED request is no longer rejected here — it's the
    # "remove a friend" action now (see RemoveFriendTests), which either
    # party can do, not just the original sender. That behavior lives in
    # its own test class rather than this one.

    def test_unknown_request_id_is_a_404(self):
        response = self.client.delete(reverse('social:friend_request', args=[999999]))
        self.assertEqual(response.status_code, 404)


class FriendBioVisibilityTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.other.bio = 'Sam studies math.'
        self.other.save()
        self.third.bio = 'Jordan likes chess.'
        self.third.save()

    def test_friends_see_each_others_bio(self):
        friendship = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        friendship.accept()
        data = self.client.get(reverse('social:friends')).json()
        self.assertEqual(data['friends'][0]['bio'], 'Sam studies math.')

    def test_pending_requests_show_the_bio_in_both_directions(self):
        FriendRequest.objects.create(sender=self.user, recipient=self.other)
        FriendRequest.objects.create(sender=self.third, recipient=self.user)
        data = self.client.get(reverse('social:friends')).json()
        self.assertEqual(data['sent_requests'][0]['user']['bio'], 'Sam studies math.')
        self.assertEqual(data['received_requests'][0]['user']['bio'], 'Jordan likes chess.')

    def test_a_friends_profile_page_includes_their_bio(self):
        friendship = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        friendship.accept()
        data = self.client.get(reverse('social:friend_profile', args=[friendship.pk])).json()
        self.assertEqual(data['user']['bio'], 'Sam studies math.')

    def test_strangers_and_declined_requests_never_expose_a_bio(self):
        declined = FriendRequest.objects.create(sender=self.third, recipient=self.user)
        declined.decline()
        FriendRequest.objects.create(sender=self.other, recipient=self.third)
        data = self.client.get(reverse('social:friends')).json()
        self.assertEqual(data, {'friends': [], 'received_requests': [], 'sent_requests': []})


class CreateFoodPostTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('social:posts')

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type='application/json')

    def test_creates_a_post_with_only_the_required_fields(self):
        response = self.post({'place_name': 'Mamoun\'s', 'description': 'Best falafel near campus.'})
        self.assertEqual(response.status_code, 201)
        post = FoodPost.objects.get()
        self.assertEqual(post.place_name, 'Mamoun\'s')
        self.assertEqual(post.description, 'Best falafel near campus.')
        self.assertEqual(post.location, '')
        self.assertEqual(post.cuisine, '')
        self.assertIsNone(post.rating)
        payload = response.json()['post']
        self.assertEqual(payload['id'], post.pk)
        self.assertEqual(payload['place_name'], 'Mamoun\'s')
        self.assertIsNone(payload['rating'])

    def test_saves_the_optional_location_cuisine_and_rating(self):
        response = self.post({
            'place_name': 'Joe\'s Pizza',
            'description': 'Grab a plain slice.',
            'location': '7 Carmine St',
            'cuisine': 'Pizza',
            'rating': 5,
        })
        self.assertEqual(response.status_code, 201)
        post = FoodPost.objects.get()
        self.assertEqual(post.location, '7 Carmine St')
        self.assertEqual(post.cuisine, 'Pizza')
        self.assertEqual(post.rating, 5)
        payload = response.json()['post']
        self.assertEqual(payload['location'], '7 Carmine St')
        self.assertEqual(payload['cuisine'], 'Pizza')
        self.assertEqual(payload['rating'], 5)

    def test_post_persists_and_shows_in_the_feed(self):
        self.post({'place_name': 'Taiwan Pork Chop House', 'description': 'Cheap and filling.'})
        feed = self.client.get(self.url).json()['posts']
        self.assertEqual([post['place_name'] for post in feed], ['Taiwan Pork Chop House'])

    def test_requires_a_place_name_and_description(self):
        response = self.post({'place_name': '', 'description': ''})
        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertEqual(errors['place_name'], ['Enter the name of the restaurant or food place.'])
        self.assertEqual(errors['description'], ['Add a description or recommendation.'])
        self.assertFalse(FoodPost.objects.exists())

    def test_whitespace_only_required_fields_are_rejected(self):
        response = self.post({'place_name': '   ', 'description': '\n  '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()['errors']), {'place_name', 'description'})
        self.assertFalse(FoodPost.objects.exists())

    def test_missing_fields_are_rejected(self):
        response = self.post({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()['errors']), {'place_name', 'description'})
        self.assertFalse(FoodPost.objects.exists())

    def test_rating_must_be_from_1_to_5(self):
        for rating in [0, 6, 'abc', 3.5]:
            with self.subTest(rating=rating):
                response = self.post({'place_name': 'Somewhere', 'description': 'Good.', 'rating': rating})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['errors']['rating'], ['Choose a rating from 1 to 5.'])
        self.assertFalse(FoodPost.objects.exists())

    def test_an_empty_rating_is_saved_as_no_rating(self):
        for rating in [None, '']:
            with self.subTest(rating=rating):
                response = self.post({'place_name': 'Somewhere', 'description': 'Good.', 'rating': rating})
                self.assertEqual(response.status_code, 201)
                self.assertIsNone(response.json()['post']['rating'])

    def test_post_belongs_to_the_logged_in_user(self):
        response = self.post({'place_name': 'Xi\'an Famous Foods', 'description': 'Spicy noodles.'})
        self.assertEqual(FoodPost.objects.get().author, self.user)
        self.assertEqual(response.json()['post']['author']['email'], 'alex@nyu.edu')

    def test_author_in_the_request_body_is_ignored(self):
        self.post({
            'place_name': 'Xi\'an Famous Foods',
            'description': 'Spicy noodles.',
            'author': self.other.pk,
            'author_id': self.other.pk,
        })
        self.assertEqual(FoodPost.objects.get().author, self.user)
        self.assertFalse(self.other.food_posts.exists())

    def test_logged_out_user_cannot_post(self):
        self.client.logout()
        response = self.post({'place_name': 'Somewhere', 'description': 'Good.'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(FoodPost.objects.exists())

    def test_rejects_invalid_json(self):
        response = self.client.post(self.url, '{not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'Invalid JSON.')
        self.assertFalse(FoodPost.objects.exists())


class FoodFeedTests(SocialTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('social:posts')

    def test_lists_every_student_s_posts_newest_first(self):
        oldest = FoodPost.objects.create(author=self.other, place_name='Oldest', description='First.')
        middle = FoodPost.objects.create(author=self.user, place_name='Middle', description='Second.')
        newest = FoodPost.objects.create(author=self.third, place_name='Newest', description='Third.')
        FoodPost.objects.filter(pk=oldest.pk).update(created_at=timezone.now() - timedelta(days=2))
        FoodPost.objects.filter(pk=middle.pk).update(created_at=timezone.now() - timedelta(days=1))

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        posts = response.json()['posts']
        self.assertEqual([post['id'] for post in posts], [newest.pk, middle.pk, oldest.pk])

    def test_posts_created_at_the_same_time_are_still_newest_first(self):
        first = FoodPost.objects.create(author=self.user, place_name='First', description='a')
        second = FoodPost.objects.create(author=self.user, place_name='Second', description='b')
        FoodPost.objects.update(created_at=timezone.now())
        posts = self.client.get(self.url).json()['posts']
        self.assertEqual([post['id'] for post in posts], [second.pk, first.pk])

    def test_each_post_includes_its_author(self):
        FoodPost.objects.create(author=self.other, place_name='Katz\'s', description='Pastrami.', rating=4)
        post = self.client.get(self.url).json()['posts'][0]
        self.assertEqual(post['author']['first_name'], 'Sam')
        self.assertEqual(post['author']['last_name'], 'Lee')
        self.assertEqual(post['author']['email'], 'sam@nyu.edu')
        self.assertIsNone(post['author']['profile_picture'])
        self.assertEqual(post['rating'], 4)
        self.assertIn('created_at', post)

    def test_feed_does_not_expose_author_bio(self):
        self.other.bio = 'Sam studies math.'
        self.other.save()
        FoodPost.objects.create(author=self.other, place_name='Katz\'s', description='Pastrami.')
        posts = self.client.get(self.url).json()['posts']
        self.assertNotIn('bio', posts[0]['author'])

        self.user.bio = 'Alex likes ramen.'
        self.user.save()
        response = self.client.post(
            self.url,
            json.dumps({'place_name': 'Ippudo', 'description': 'Rich broth.'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('bio', response.json()['post']['author'])

    def test_empty_feed(self):
        self.assertEqual(self.client.get(self.url).json(), {'posts': []})

    def test_logged_out_user_cannot_view_the_feed(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_only_get_and_post_are_allowed(self):
        self.assertEqual(self.client.delete(self.url).status_code, 405)


class FoodPostModelTests(SocialTestCase):
    def test_database_rejects_a_rating_outside_1_to_5(self):
        for rating in [0, 6]:
            with self.subTest(rating=rating), self.assertRaises(IntegrityError), transaction.atomic():
                FoodPost.objects.create(author=self.user, place_name='X', description='Y', rating=rating)

    def test_deleting_an_account_deletes_its_posts(self):
        FoodPost.objects.create(author=self.other, place_name='X', description='Y')
        self.other.delete()
        self.assertFalse(FoodPost.objects.exists())
