import json

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import DirectMessage, FriendRequest


class DirectMessageTests(TestCase):
    def setUp(self):
        self.alex = User.objects.create_user(username='alex@nyu.edu', email='alex@nyu.edu', password='test123')
        self.sam = User.objects.create_user(
            username='sam@nyu.edu', email='sam@nyu.edu', first_name='Sam', last_name='Lee', password='test123',
        )
        self.jordan = User.objects.create_user(username='jordan@nyu.edu', email='jordan@nyu.edu', password='test123')
        self.url = reverse('social:conversation', args=[self.sam.pk])
        self.client.force_login(self.alex)

    def befriend(self):
        friendship = FriendRequest.objects.create(sender=self.sam, recipient=self.alex)
        friendship.accept()
        return friendship

    def send(self, body):
        return self.client.post(self.url, json.dumps(body), content_type='application/json')

    def test_requires_login_for_reading_and_sending(self):
        self.befriend()
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.send({'body': 'Hello'}).status_code, 401)

    def test_accepted_friendship_in_either_direction_permits_messaging(self):
        self.befriend()
        response = self.send({'body': '  Hi Sam!  '})
        self.assertEqual(response.status_code, 201)
        message = DirectMessage.objects.get()
        self.assertEqual(message.sender, self.alex)
        self.assertEqual(message.recipient, self.sam)
        self.assertEqual(message.body, 'Hi Sam!')
        payload = response.json()['message']
        self.assertEqual(payload['sender_id'], self.alex.pk)
        self.assertTrue(payload['is_mine'])
        self.assertEqual(payload['sender_name'], self.alex.email)
        self.assertEqual(payload['body'], 'Hi Sam!')
        self.assertTrue(payload['created_at'])

        self.client.force_login(self.sam)
        reply_url = reverse('social:conversation', args=[self.alex.pk])
        self.assertEqual(
            self.client.post(reply_url, json.dumps({'body': 'Hello back'}), content_type='application/json').status_code, 201,
        )
        messages = self.client.get(reply_url).json()['messages']
        self.assertEqual([m['body'] for m in messages], ['Hi Sam!', 'Hello back'])
        self.assertEqual([m['is_mine'] for m in messages], [False, True])

    def test_pending_and_declined_requests_do_not_grant_access(self):
        request = FriendRequest.objects.create(sender=self.alex, recipient=self.sam)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.send({'body': 'Nope'}).status_code, 404)
        request.decline()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_strangers_cannot_read_or_send_other_users_conversations(self):
        self.befriend()
        DirectMessage.objects.create(sender=self.sam, recipient=self.alex, body='Private')
        self.client.force_login(self.jordan)
        self.assertEqual(self.client.get(reverse('social:conversation', args=[self.alex.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.send({'body': 'No access'}).status_code, 404)

    def test_cannot_message_yourself_or_unknown_user(self):
        self.assertEqual(self.client.get(reverse('social:conversation', args=[self.alex.pk])).status_code, 404)
        self.assertEqual(self.send({'body': 'Hi'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('social:conversation', args=[999999])).status_code, 404)

    def test_rejects_blank_messages_malformed_json_and_invalid_payloads(self):
        self.befriend()
        for payload in ({'body': ''}, {'body': '   '}, {}, {'body': 123}, {'body': 'x' * 2001}):
            with self.subTest(payload=str(payload)[:30]):
                response = self.send(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('body', response.json()['errors'])
        self.assertEqual(self.send([]).status_code, 400)
        self.assertEqual(self.client.post(self.url, '{', content_type='application/json').status_code, 400)
        self.assertEqual(DirectMessage.objects.count(), 0)

    def test_history_orders_both_senders_by_timestamp_and_id(self):
        self.befriend()
        first = DirectMessage.objects.create(sender=self.sam, recipient=self.alex, body='First')
        second = DirectMessage.objects.create(sender=self.alex, recipient=self.sam, body='Second')
        third = DirectMessage.objects.create(sender=self.sam, recipient=self.alex, body='Third')
        # Ties still render consistently using the primary key.
        DirectMessage.objects.filter(pk__in=[first.pk, second.pk, third.pk]).update(created_at=first.created_at)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['friend']['email'], self.sam.email)
        self.assertEqual(data['friend']['first_name'], 'Sam')
        self.assertEqual([m['id'] for m in data['messages']], [first.pk, second.pk, third.pk])
        self.assertEqual([m['sender_name'] for m in data['messages']], ['Sam Lee', self.alex.email, 'Sam Lee'])
        self.assertEqual([m['is_mine'] for m in data['messages']], [False, True, False])
        self.assertTrue(all('created_at' in m for m in data['messages']))

    def test_empty_conversation_returns_friend_and_empty_messages(self):
        self.befriend()
        result = self.client.get(self.url).json()
        self.assertEqual(result['messages'], [])
        self.assertEqual(result['friend']['id'], self.sam.pk)

    def test_only_conversation_participants_can_read_history(self):
        self.befriend()
        DirectMessage.objects.create(sender=self.sam, recipient=self.alex, body='Between Alex and Sam')
        friendship = FriendRequest.objects.create(sender=self.sam, recipient=self.jordan)
        friendship.accept()
        self.client.force_login(self.jordan)
        result = self.client.get(reverse('social:conversation', args=[self.sam.pk])).json()
        self.assertEqual(result['messages'], [])

    def test_removing_friendship_blocks_new_messages_and_history_without_deleting_records(self):
        friendship = self.befriend()
        self.send({'body': 'Before unfriending'})
        friendship.delete()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.send({'body': 'After unfriending'}).status_code, 404)
        self.assertEqual(DirectMessage.objects.count(), 1)

    def test_database_rejects_self_messages(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DirectMessage.objects.create(sender=self.alex, recipient=self.alex, body='Self')

    def test_get_only_reads_and_post_only_sends(self):
        self.befriend()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(DirectMessage.objects.count(), 0)
        self.assertEqual(self.client.put(self.url, '{}', content_type='application/json').status_code, 405)
        self.assertEqual(DirectMessage.objects.count(), 0)
