import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import DirectMessage, FriendRequest


class AlertsTestCase(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username='me@nyu.edu', email='me@nyu.edu', password='test123')
        self.sam = User.objects.create_user(username='sam@nyu.edu', email='sam@nyu.edu', password='test123')
        self.kim = User.objects.create_user(username='kim@nyu.edu', email='kim@nyu.edu', password='test123')
        self.client.force_login(self.me)
        self.url = reverse('social:alerts')

    def befriend(self, other, sender=None):
        # By default they asked me; pass sender=self.me for the other direction.
        asker = sender or other
        friendship = FriendRequest.objects.create(sender=asker, recipient=other if asker == self.me else self.me)
        friendship.accept()
        return friendship

    def message(self, sender, recipient, body='hi'):
        return DirectMessage.objects.create(sender=sender, recipient=recipient, body=body)

    def alerts(self):
        return self.client.get(self.url).json()

    def turn_off(self, **fields):
        for name, value in fields.items():
            setattr(self.me, name, value)
        self.me.save()


class AlertCountTests(AlertsTestCase):
    def test_requires_login_and_get_only(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.force_login(self.me)
        self.assertEqual(self.client.post(self.url, '{}', content_type='application/json').status_code, 405)

    def test_nothing_new_means_zeroes(self):
        self.assertEqual(self.alerts(), {'friend_requests': 0, 'unread_messages': 0, 'unread_by_friend': {}})

    def test_counts_pending_requests_sent_to_me_only(self):
        FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        FriendRequest.objects.create(sender=self.me, recipient=self.kim)  # I sent this one
        self.assertEqual(self.alerts()['friend_requests'], 1)

    def test_answered_requests_stop_counting(self):
        accepted = FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        declined = FriendRequest.objects.create(sender=self.kim, recipient=self.me)
        self.assertEqual(self.alerts()['friend_requests'], 2)
        accepted.accept()
        declined.decline()
        self.assertEqual(self.alerts()['friend_requests'], 0)

    def test_counts_unread_messages_per_friend(self):
        self.befriend(self.sam)
        self.befriend(self.kim)
        self.message(self.sam, self.me)
        self.message(self.sam, self.me)
        self.message(self.kim, self.me)
        data = self.alerts()
        self.assertEqual(data['unread_messages'], 3)
        self.assertEqual(data['unread_by_friend'], {str(self.sam.pk): 2, str(self.kim.pk): 1})

    def test_my_own_messages_are_never_unread(self):
        self.befriend(self.sam)
        self.message(self.me, self.sam)
        self.assertEqual(self.alerts()['unread_messages'], 0)

    def test_messages_between_other_people_are_not_counted(self):
        self.befriend(self.sam)
        self.message(self.sam, self.kim)
        self.assertEqual(self.alerts()['unread_messages'], 0)

    def test_messages_from_someone_who_is_no_longer_a_friend_are_not_counted(self):
        friendship = self.befriend(self.sam)
        self.message(self.sam, self.me)
        self.assertEqual(self.alerts()['unread_messages'], 1)
        friendship.delete()
        self.assertEqual(self.alerts()['unread_messages'], 0)

    def test_friendships_in_either_direction_count(self):
        self.befriend(self.sam, sender=self.me)  # I sent the request, they accepted
        self.message(self.sam, self.me)
        self.assertEqual(self.alerts()['unread_by_friend'], {str(self.sam.pk): 1})

    def test_one_students_alerts_do_not_include_anothers(self):
        self.befriend(self.sam)
        self.message(self.sam, self.me)
        FriendRequest.objects.create(sender=self.kim, recipient=self.me)
        self.client.force_login(self.sam)
        # Sam's only alert is that I accepted the request Sam sent. My unread
        # message and Kim's request to me are not Sam's to see.
        self.assertEqual(self.alerts(), {'friend_requests': 1, 'unread_messages': 0, 'unread_by_friend': {}})


class AlertSettingTests(AlertsTestCase):
    def setUp(self):
        super().setUp()
        self.befriend(self.sam)
        self.message(self.sam, self.me)
        FriendRequest.objects.create(sender=self.kim, recipient=self.me)

    def test_both_on_by_default(self):
        data = self.alerts()
        self.assertEqual((data['friend_requests'], data['unread_messages']), (1, 1))

    def test_friend_request_alerts_off_only_silences_requests(self):
        self.turn_off(friend_request_alerts_enabled=False)
        data = self.alerts()
        self.assertEqual((data['friend_requests'], data['unread_messages']), (0, 1))

    def test_message_alerts_off_only_silences_messages(self):
        self.turn_off(message_alerts_enabled=False)
        data = self.alerts()
        self.assertEqual((data['friend_requests'], data['unread_messages'], data['unread_by_friend']), (1, 0, {}))

    def test_turning_alerts_off_does_not_hide_the_requests_themselves(self):
        self.turn_off(friend_request_alerts_enabled=False)
        received = self.client.get(reverse('social:friends')).json()['received_requests']
        self.assertEqual(len(received), 1)


class ReadTrackingTests(AlertsTestCase):
    def setUp(self):
        super().setUp()
        self.befriend(self.sam)
        self.conversation = reverse('social:conversation', args=[self.sam.pk])

    def test_new_messages_start_unread(self):
        self.assertIsNone(self.message(self.sam, self.me).read_at)

    def test_opening_the_conversation_reads_what_they_sent_me(self):
        incoming = self.message(self.sam, self.me)
        self.client.get(self.conversation)
        incoming.refresh_from_db()
        self.assertIsNotNone(incoming.read_at)
        self.assertEqual(self.alerts()['unread_messages'], 0)

    def test_it_only_clears_that_friends_messages(self):
        self.befriend(self.kim)
        self.message(self.sam, self.me)
        self.message(self.kim, self.me)
        self.client.get(self.conversation)
        self.assertEqual(self.alerts()['unread_by_friend'], {str(self.kim.pk): 1})

    def test_opening_it_does_not_mark_my_own_messages_or_anyone_elses_read(self):
        mine = self.message(self.me, self.sam)
        between_others = self.message(self.sam, self.kim)
        self.client.get(self.conversation)
        mine.refresh_from_db()
        between_others.refresh_from_db()
        self.assertIsNone(mine.read_at)
        self.assertIsNone(between_others.read_at)

    def test_the_other_person_reading_does_not_read_mine_for_me(self):
        incoming = self.message(self.sam, self.me)
        self.client.force_login(self.sam)
        self.client.get(self.conversation.replace(str(self.sam.pk), str(self.me.pk)))
        incoming.refresh_from_db()
        self.assertIsNone(incoming.read_at)

    def test_sending_a_message_does_not_read_theirs(self):
        incoming = self.message(self.sam, self.me)
        self.client.post(self.conversation, json.dumps({'body': 'hello'}), content_type='application/json')
        incoming.refresh_from_db()
        self.assertIsNone(incoming.read_at)

    def test_reading_still_happens_with_message_alerts_off(self):
        self.turn_off(message_alerts_enabled=False)
        incoming = self.message(self.sam, self.me)
        self.client.get(self.conversation)
        incoming.refresh_from_db()
        self.assertIsNotNone(incoming.read_at)
        self.turn_off(message_alerts_enabled=True)
        self.assertEqual(self.alerts()['unread_messages'], 0)

    def test_a_stranger_cannot_mark_messages_read(self):
        stranger = User.objects.create_user(username='x@nyu.edu', email='x@nyu.edu', password='test123')
        incoming = self.message(self.sam, self.me)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.conversation).status_code, 404)
        incoming.refresh_from_db()
        self.assertIsNone(incoming.read_at)

    def test_reading_twice_keeps_the_first_read_time(self):
        incoming = self.message(self.sam, self.me)
        self.client.get(self.conversation)
        incoming.refresh_from_db()
        first = incoming.read_at
        self.client.get(self.conversation)
        incoming.refresh_from_db()
        self.assertEqual(incoming.read_at, first)


class FriendListUnreadTests(AlertsTestCase):
    """The conversation list shows how many unread messages each friend has sent."""

    def unread(self):
        return {item['id']: item['unread_messages'] for item in self.client.get(reverse('social:friends')).json()['friends']}

    def test_each_friend_carries_their_unread_count(self):
        self.befriend(self.sam)
        self.befriend(self.kim)
        self.message(self.sam, self.me)
        self.message(self.sam, self.me)
        self.assertEqual(self.unread(), {self.sam.pk: 2, self.kim.pk: 0})

    def test_it_drops_to_zero_once_the_conversation_is_opened(self):
        self.befriend(self.sam)
        self.message(self.sam, self.me)
        self.client.get(reverse('social:conversation', args=[self.sam.pk]))
        self.assertEqual(self.unread(), {self.sam.pk: 0})

    def test_it_is_zero_for_everyone_with_message_alerts_off(self):
        self.befriend(self.sam)
        self.message(self.sam, self.me)
        self.turn_off(message_alerts_enabled=False)
        self.assertEqual(self.unread(), {self.sam.pk: 0})


class AcceptedRequestAlertTests(AlertsTestCase):
    """The sender hears when a request is accepted, and only until they open Friends."""

    def send_request(self, to):
        return FriendRequest.objects.create(sender=self.me, recipient=to)

    def friends(self):
        return {item['id']: item for item in self.client.get(reverse('social:friends')).json()['friends']}

    def test_an_accepted_request_i_sent_counts_until_i_see_it(self):
        self.send_request(self.sam).accept()
        self.assertEqual(self.alerts()['friend_requests'], 1)

    def test_it_adds_to_requests_waiting_for_me(self):
        self.send_request(self.sam).accept()
        FriendRequest.objects.create(sender=self.kim, recipient=self.me)
        self.assertEqual(self.alerts()['friend_requests'], 2)

    def test_a_pending_request_i_sent_does_not_count(self):
        self.send_request(self.sam)
        self.assertEqual(self.alerts()['friend_requests'], 0)

    def test_a_declined_request_never_alerts(self):
        self.send_request(self.sam).decline()
        self.assertEqual(self.alerts()['friend_requests'], 0)

    def test_accepting_someone_elses_request_does_not_alert_me_about_it(self):
        incoming = FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        incoming.accept()
        self.assertEqual(self.alerts()['friend_requests'], 0)
        self.assertFalse(self.friends()[self.sam.pk]['is_new'])

    def test_the_friends_list_marks_who_is_new(self):
        self.send_request(self.sam).accept()
        self.befriend(self.kim)  # Kim asked me, so she is not "new" to me
        friends = self.friends()
        self.assertTrue(friends[self.sam.pk]['is_new'])
        self.assertFalse(friends[self.kim.pk]['is_new'])

    def test_loading_the_friends_list_does_not_clear_it(self):
        # MessagesPage uses the same list, so only the explicit call clears it.
        self.send_request(self.sam).accept()
        self.friends()
        self.assertEqual(self.alerts()['friend_requests'], 1)
        self.assertTrue(self.friends()[self.sam.pk]['is_new'])

    def test_marking_seen_clears_the_alert_and_the_new_flag(self):
        self.send_request(self.sam).accept()
        self.assertEqual(self.client.post(reverse('social:friends_seen')).status_code, 200)
        self.assertEqual(self.alerts()['friend_requests'], 0)
        self.assertFalse(self.friends()[self.sam.pk]['is_new'])

    def test_seen_only_clears_my_own_requests(self):
        mine = self.send_request(self.sam)
        mine.accept()
        theirs = FriendRequest.objects.create(sender=self.sam, recipient=self.kim)
        theirs.accept()
        self.client.post(reverse('social:friends_seen'))
        theirs.refresh_from_db()
        self.assertIsNone(theirs.response_seen_at)

    def test_seen_does_not_touch_requests_waiting_for_me(self):
        FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        self.client.post(reverse('social:friends_seen'))
        self.assertEqual(self.alerts()['friend_requests'], 1)

    def test_seen_requires_login_and_post(self):
        self.assertEqual(self.client.get(reverse('social:friends_seen')).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('social:friends_seen')).status_code, 401)

    def test_marking_seen_works_even_with_alerts_off(self):
        self.send_request(self.sam).accept()
        self.turn_off(friend_request_alerts_enabled=False)
        self.assertEqual(self.alerts()['friend_requests'], 0)
        self.client.post(reverse('social:friends_seen'))
        self.turn_off(friend_request_alerts_enabled=True)
        self.assertEqual(self.alerts()['friend_requests'], 0)

    def test_alerts_off_hides_the_count_but_the_new_flag_remains(self):
        self.send_request(self.sam).accept()
        self.turn_off(friend_request_alerts_enabled=False)
        self.assertEqual(self.alerts()['friend_requests'], 0)
        self.assertTrue(self.friends()[self.sam.pk]['is_new'])

    def test_sending_a_request_back_accepts_theirs_and_alerts_them(self):
        # Sam asked me; when I ask Sam back it becomes a friendship Sam hasn't seen.
        FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        self.client.post(
            reverse('social:friend_requests'), json.dumps({'email': 'sam@nyu.edu'}), content_type='application/json',
        )
        self.client.force_login(self.sam)
        self.assertEqual(self.alerts()['friend_requests'], 1)

    def test_accepting_through_the_api_alerts_the_sender(self):
        incoming = FriendRequest.objects.create(sender=self.sam, recipient=self.me)
        self.client.patch(
            reverse('social:friend_request', args=[incoming.pk]), json.dumps({'status': 'accepted'}), content_type='application/json',
        )
        self.client.force_login(self.sam)
        self.assertEqual(self.alerts()['friend_requests'], 1)
        self.assertTrue(self.friends()[self.me.pk]['is_new'])

    def test_removing_the_friend_takes_the_alert_away(self):
        friendship = self.send_request(self.sam)
        friendship.accept()
        friendship.delete()
        self.assertEqual(self.alerts()['friend_requests'], 0)
