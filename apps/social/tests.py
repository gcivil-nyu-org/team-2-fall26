import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import FriendRequest


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

    def test_declined_requests_are_not_listed_anywhere(self):
        declined = FriendRequest.objects.create(sender=self.user, recipient=self.other)
        declined.decline()
        data = self.client.get(self.url).json()
        self.assertEqual(data, {'friends': [], 'received_requests': [], 'sent_requests': []})


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

    def test_cannot_cancel_an_already_accepted_request(self):
        self.outgoing.accept()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(FriendRequest.objects.filter(pk=self.outgoing.pk).exists())

    def test_unknown_request_id_is_a_404(self):
        response = self.client.delete(reverse('social:friend_request', args=[999999]))
        self.assertEqual(response.status_code, 404)
