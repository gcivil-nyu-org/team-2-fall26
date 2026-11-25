from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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
    # When the sender saw that this request was accepted. Null on an accepted
    # request means "new" — it drives the Friends alert (#37).
    response_seen_at = models.DateTimeField(blank=True, null=True)

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
    # Blank only when the message shares a post without a note (#22).
    body = models.CharField(max_length=2000, blank=True)
    # #22: a food post shared into the conversation. If the post is deleted
    # later the message stays, and shares_post lets the conversation say the
    # post is no longer available instead of showing an empty message.
    shared_post = models.ForeignKey(
        'FoodPost', on_delete=models.SET_NULL, null=True, blank=True, related_name='shares',
    )
    shares_post = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # When the recipient opened the conversation. Null means unread (#37).
    read_at = models.DateTimeField(blank=True, null=True)

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


class FoodPostQuerySet(models.QuerySet):
    def community(self):
        # #47: the posts other students can browse. Posts by a deactivated
        # account stay hidden (and come back if it's reactivated); a deleted
        # account's posts are already gone with it.
        return self.filter(author__is_active=True)

    def with_saved(self, user):
        # #53: marks each post the student has saved, for the Save button.
        return self.annotate(is_saved=models.Exists(SavedPost.objects.filter(user=user, post=models.OuterRef('pk'))))

    def with_comment_count(self):
        # #49: comments the community can see, so the count matches the list.
        return self.annotate(comment_count=models.Count(
            'comments', filter=models.Q(comments__author__is_active=True), distinct=True,
        ))


class FoodPost(models.Model):
    # #46: a student's recommendation for a place to eat, shown in the
    # community feed (E5). Photos are a follow-up that will reuse the
    # profile-picture upload setup from #84.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='food_posts',
    )
    place_name = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    cuisine = models.CharField(max_length=100, blank=True)
    rating = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FoodPostQuerySet.as_manager()

    class Meta:
        # -id breaks ties between posts created in the same instant, so the
        # feed's newest-first order is always stable.
        ordering = ['-created_at', '-id']
        constraints = [
            # The form already limits ratings to 1–5; this keeps the admin or
            # any future caller from saving something the feed can't display.
            models.CheckConstraint(
                condition=models.Q(rating__isnull=True) | models.Q(rating__gte=1, rating__lte=5),
                name='food_post_rating_1_to_5',
            ),
        ]

    def __str__(self):
        return self.place_name


class SavedPost(models.Model):
    # #53: a food post a student saved to try later. Saves belong to the
    # student; nobody else can see them.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_posts',
    )
    post = models.ForeignKey(FoodPost, on_delete=models.CASCADE, related_name='saves')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Most recently saved first.
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='saved_post_once_per_user'),
        ]

    def __str__(self):
        return f'{self.user} saved {self.post}'


class PostCommentQuerySet(models.QuerySet):
    def community(self):
        # Like posts, comments by a deactivated account stay hidden until
        # it's reactivated (#49).
        return self.filter(author__is_active=True)


class PostComment(models.Model):
    # #49: a student's comment on a food post.
    post = models.ForeignKey(FoodPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_comments',
    )
    body = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PostCommentQuerySet.as_manager()

    class Meta:
        # Oldest first, so a discussion reads top to bottom.
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.author} on {self.post}'
