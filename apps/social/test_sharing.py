import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import DirectMessage, FoodPost, FriendRequest


class ShareFoodPostTests(TestCase):
    # #22: sharing a community post with a friend.
    def setUp(self):
        self.alex = User.objects.create_user(username='alex@nyu.edu', email='alex@nyu.edu', password='test123')
        self.sam = User.objects.create_user(
            username='sam@nyu.edu', email='sam@nyu.edu', first_name='Sam', last_name='Lee', password='test123',
        )
        self.jordan = User.objects.create_user(
            username='jordan@nyu.edu', email='jordan@nyu.edu', first_name='Jordan', password='test123',
        )
        self.post = FoodPost.objects.create(
            author=self.jordan, place_name="Joe's Pizza", description='Grab a plain slice.',
            location='7 Carmine St', cuisine='Pizza', rating=5,
        )
        FriendRequest.objects.create(sender=self.sam, recipient=self.alex).accept()
        self.client.force_login(self.alex)

    def share(self, data, pk=None):
        url = reverse('social:post_share', args=[pk or self.post.pk])
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def conversation(self, viewer, friend):
        self.client.force_login(viewer)
        return self.client.get(reverse('social:conversation', args=[friend.pk])).json()['messages']

    def test_sharing_sends_the_post_to_the_friend_as_a_message(self):
        response = self.share({'friend_id': self.sam.pk, 'note': '  You have to try this  '})
        self.assertEqual(response.status_code, 201)
        message = DirectMessage.objects.get()
        self.assertEqual((message.sender, message.recipient), (self.alex, self.sam))
        self.assertEqual(message.shared_post, self.post)
        self.assertTrue(message.shares_post)
        self.assertEqual(message.body, 'You have to try this')
        payload = response.json()['message']
        self.assertTrue(payload['is_mine'])
        self.assertEqual(payload['shared_post']['id'], self.post.pk)

    def test_note_is_optional(self):
        self.assertEqual(self.share({'friend_id': self.sam.pk}).status_code, 201)
        self.assertEqual(self.share({'friend_id': self.sam.pk, 'note': '   '}).status_code, 201)
        self.assertEqual(list(DirectMessage.objects.values_list('body', flat=True)), ['', ''])

    def test_shared_post_shows_original_content_and_author_to_both_people(self):
        self.share({'friend_id': self.sam.pk})
        for viewer, friend in ((self.alex, self.sam), (self.sam, self.alex)):
            with self.subTest(viewer=viewer.email):
                [message] = self.conversation(viewer, friend)
                shared = message['shared_post']
                self.assertTrue(shared['available'])
                self.assertEqual(shared['id'], self.post.pk)
                self.assertEqual(shared['place_name'], "Joe's Pizza")
                self.assertEqual(shared['description'], 'Grab a plain slice.')
                self.assertEqual((shared['location'], shared['cuisine'], shared['rating']), ('7 Carmine St', 'Pizza', 5))
                self.assertEqual(shared['author']['id'], self.jordan.pk)
                self.assertEqual(shared['author']['first_name'], 'Jordan')
                # Bios are friends-only (#35), and the author need not be a friend.
                self.assertNotIn('bio', shared['author'])
                self.assertNotIn('is_saved', shared)

    def test_friend_can_open_the_shared_post(self):
        self.share({'friend_id': self.sam.pk})
        [message] = self.conversation(self.sam, self.alex)
        response = self.client.get(reverse('social:post', args=[message['shared_post']['id']]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['post']['place_name'], "Joe's Pizza")

    def test_plain_messages_have_no_shared_post(self):
        self.client.post(
            reverse('social:conversation', args=[self.sam.pk]), json.dumps({'body': 'Hi'}),
            content_type='application/json',
        )
        [message] = self.conversation(self.alex, self.sam)
        self.assertIsNone(message['shared_post'])

    def test_cannot_share_with_someone_who_is_not_a_friend(self):
        pending = FriendRequest.objects.create(sender=self.alex, recipient=self.jordan)
        self.assertEqual(self.share({'friend_id': self.jordan.pk}).status_code, 404)
        pending.decline()
        self.assertEqual(self.share({'friend_id': self.jordan.pk}).status_code, 404)
        for friend_id in (self.alex.pk, 999999):
            with self.subTest(friend_id=friend_id):
                self.assertEqual(self.share({'friend_id': friend_id}).status_code, 404)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_cannot_share_after_unfriending(self):
        FriendRequest.objects.accepted().between(self.alex, self.sam).delete()
        self.assertEqual(self.share({'friend_id': self.sam.pk}).status_code, 404)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_cannot_share_a_missing_or_hidden_post(self):
        self.assertEqual(self.share({'friend_id': self.sam.pk}, pk=999999).status_code, 404)
        self.jordan.is_active = False
        self.jordan.save()
        self.assertEqual(self.share({'friend_id': self.sam.pk}).status_code, 404)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_deleted_post_stays_in_the_conversation_as_unavailable(self):
        self.share({'friend_id': self.sam.pk, 'note': 'Try this'})
        self.post.delete()
        [message] = self.conversation(self.sam, self.alex)
        self.assertEqual(message['shared_post'], {'available': False})
        self.assertEqual(message['body'], 'Try this')

    def test_post_by_a_deactivated_author_is_unavailable_until_reactivated(self):
        self.share({'friend_id': self.sam.pk})
        self.jordan.is_active = False
        self.jordan.save()
        self.assertEqual(self.conversation(self.sam, self.alex)[0]['shared_post'], {'available': False})
        self.jordan.is_active = True
        self.jordan.save()
        self.assertTrue(self.conversation(self.sam, self.alex)[0]['shared_post']['available'])

    def test_rejects_invalid_friend_or_note(self):
        cases = [
            ({}, 'friend_id'),
            ({'friend_id': ''}, 'friend_id'),
            ({'friend_id': 'sam'}, 'friend_id'),
            ({'friend_id': 0}, 'friend_id'),
            ({'friend_id': True}, 'friend_id'),
            ({'friend_id': self.sam.pk, 'note': 123}, 'note'),
            ({'friend_id': self.sam.pk, 'note': 'x' * 2001}, 'note'),
        ]
        for data, field in cases:
            with self.subTest(data=str(data)[:40]):
                response = self.share(data)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()['errors'])
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_rejects_malformed_json(self):
        url = reverse('social:post_share', args=[self.post.pk])
        self.assertEqual(self.client.post(url, '{', content_type='application/json').status_code, 400)
        self.assertEqual(self.share([]).status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.share({'friend_id': self.sam.pk}).status_code, 401)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_only_post_is_allowed(self):
        url = reverse('social:post_share', args=[self.post.pk])
        for method in (self.client.get, self.client.put, self.client.delete):
            with self.subTest(method=method.__name__):
                self.assertEqual(method(url).status_code, 405)
