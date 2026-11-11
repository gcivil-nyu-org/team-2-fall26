from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class FriendRequestQuerySet(models.QuerySet):
    def involving(self, user):
        return self.filter(models.Q(sender=user) | models.Q(recipient=user))

    def between(self, user_a, user_b):
        # Either direction counts as "between" these two users — a friend
        # request from A to B and one from B to A describe the same pair.
        return self.filter(
            models.Q(sender=user_a, recipient=user_b) | models.Q(sender=user_b, recipient=user_a)
        )

    def pending(self):
        return self.filter(status=FriendRequest.Status.PENDING)

    def accepted(self):
        return self.filter(status=FriendRequest.Status.ACCEPTED)


class FriendRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        DECLINED = 'declined', 'Declined'

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_friend_requests',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_friend_requests',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    objects = FriendRequestQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # A belt-and-suspenders guard against ever creating a self-request —
            # the view already excludes this, but a bug or a future caller
            # (e.g. the admin) shouldn't be able to slip one past the database.
            models.CheckConstraint(
                condition=~models.Q(sender=models.F('recipient')),
                name='friend_request_not_self',
            ),
            # Only one *pending* request per direction at a time. A second
            # request in the same direction while one is still outstanding
            # would just be a confusing duplicate; the view turns a reverse
            # pending request into an acceptance instead of a new row, so this
            # only needs to stop same-direction duplicates.
            models.UniqueConstraint(
                fields=['sender', 'recipient'],
                condition=models.Q(status='pending'),
                name='unique_pending_friend_request_per_direction',
            ),
        ]

    def __str__(self):
        return f'{self.sender} -> {self.recipient} ({self.status})'

    def clean(self):
        super().clean()
        # The view is the only normal way to create a FriendRequest, and it
        # already enforces these rules before ever calling .save(). This is a
        # second line of defense for anything that goes through a ModelForm
        # instead — the Django admin, above all — so a mistake there raises a
        # clean ValidationError rather than a raw IntegrityError (self-request)
        # or silently corrupt data (a second request between two people who
        # are already friends, which nothing at the database level rules out).
        if self.sender_id and self.recipient_id:
            if self.sender_id == self.recipient_id:
                raise ValidationError('A friend request cannot be sent to yourself.')
            if self.status != FriendRequest.Status.DECLINED:
                already_friends = (
                    FriendRequest.objects.between(self.sender, self.recipient)
                    .accepted()
                    .exclude(pk=self.pk)
                    .exists()
                )
                if already_friends:
                    raise ValidationError('These two users are already friends.')

    def other(self, viewer):
        return self.recipient if self.sender_id == viewer.pk else self.sender

    def accept(self):
        self.status = FriendRequest.Status.ACCEPTED
        self.responded_at = timezone.now()
        self.save(update_fields=['status', 'responded_at'])

    def decline(self):
        self.status = FriendRequest.Status.DECLINED
        self.responded_at = timezone.now()
        self.save(update_fields=['status', 'responded_at'])


class DirectMessage(models.Model):
    # Conversation identity is the pair of users, not a FriendRequest id.
    # If a friendship is removed, the stored messages remain but the API
    # denies access until the two users become friends again.
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_direct_messages',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_direct_messages',
    )
    body = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(sender=models.F('recipient')),
                name='direct_message_not_self',
            ),
        ]

    def __str__(self):
        return f'Message {self.pk} from {self.sender_id} to {self.recipient_id}'
