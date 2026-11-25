import json

from django.db import IntegrityError, models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User

from .forms import (
    FoodPostForm, PostCommentForm, ReportContentForm, RespondToFriendRequestForm, SendDirectMessageForm,
    SendFriendRequestForm, ShareFoodPostForm,
)
from .models import ContentReport, DirectMessage, FoodPost, FriendRequest, PostComment, SavedPost


def _json_body(request):
    try:
        return json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _unauthorized():
    return JsonResponse({'detail': 'Authentication required.'}, status=401)


def _errors(form):
    return {
        field: [item['message'] for item in messages.get_json_data()]
        for field, messages in form.errors.items()
    }


ANONYMOUS_NAME = 'SemesterPilot student'


def _display_name(user):
    """A name to show other students: never falls back to a hidden email (#31)."""
    name = ' '.join(filter(None, [user.first_name, user.last_name]))
    return name or (user.email if user.show_email else ANONYMOUS_NAME)


def _user_summary(user):
    # Every caller passes someone *other than* the viewer (a friend, or the
    # other side of a request), so this is where a student's privacy
    # settings (#31) take effect. Hidden fields are blanked here rather than
    # in the frontend so they never reach another student's browser at all.
    # The name stays visible: friends need it to tell who is who.
    return {
        'id': user.pk,
        'email': user.email if user.show_email else None,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'bio': user.bio if user.show_bio else '',
        # Lets the frontend show a real photo on friend requests and in the
        # friends list (falling back to an initial when there isn't one) -
        # same shape apps/api/views.py's _user_payload already uses for a
        # user's own profile.
        'profile_picture': user.profile_picture.url if user.profile_picture and user.show_profile_picture else None,
    }


def _request_payload(friend_request, viewer):
    return {
        'id': friend_request.pk,
        'status': friend_request.status,
        'direction': 'sent' if friend_request.sender_id == viewer.pk else 'received',
        'user': _user_summary(friend_request.other(viewer)),
        'created_at': friend_request.created_at.isoformat(),
    }


def _post_payload(post, viewer):
    return {
        'id': post.pk,
        'place_name': post.place_name,
        'description': post.description,
        'location': post.location,
        'cuisine': post.cuisine,
        'rating': post.rating,
        'author': _public_author(post.author),
        # #51/#52: lets the post page show Edit and Delete to its author. The
        # server still checks ownership on every change.
        'is_author': post.author_id == viewer.pk,
        'created_at': post.created_at.isoformat(),
        # #53: whether the student viewing it has saved it.
        'is_saved': bool(getattr(post, 'is_saved', False)),
        # #49: how many comments the post page will show.
        'comment_count': getattr(post, 'comment_count', 0),
        # #67: whether the student viewing it has already reported it.
        'is_reported': bool(getattr(post, 'is_reported', False)),
    }


def _public_author(user):
    # Posts and comments are seen by every student, but bios are friends-only
    # (#35), so the author summary leaves the bio out.
    return {k: v for k, v in _user_summary(user).items() if k != 'bio'}


def _comment_payload(comment, viewer):
    return {
        'id': comment.pk,
        'body': comment.body,
        'author': _public_author(comment.author),
        'created_at': comment.created_at.isoformat(),
        # #67: students can report other people's comments, once each.
        'is_author': comment.author_id == viewer.pk,
        'is_reported': bool(getattr(comment, 'is_reported', False)),
    }


def _community_posts(user):
    # Counting comments groups the query, and Django drops Meta.ordering from
    # grouped queries, so the newest-first order is spelled out here.
    return (
        FoodPost.objects.community().with_saved(user).with_reported(user).with_comment_count()
        .select_related('author').order_by('-created_at', '-id')
    )


def _unread_by_friend(user):
    # Unread messages per current friend, for the badges and the conversation
    # list (#37). Empty when the student has message alerts off. Messages left
    # behind by a removed friendship stay out, because the conversation can't
    # be opened to read them.
    if not user.message_alerts_enabled:
        return {}
    friend_ids = [friendship.other(user).pk for friendship in FriendRequest.objects.accepted().involving(user)]
    unread = (
        DirectMessage.objects.filter(recipient=user, sender__in=friend_ids, read_at__isnull=True)
        .values('sender').annotate(total=models.Count('pk'))
    )
    return {row['sender']: row['total'] for row in unread}


@require_GET
def friends_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    accepted = FriendRequest.objects.accepted().involving(request.user).select_related('sender', 'recipient')
    received = FriendRequest.objects.pending().filter(recipient=request.user).select_related('sender')
    sent = FriendRequest.objects.pending().filter(sender=request.user).select_related('recipient')
    unread = _unread_by_friend(request.user)
    friends = sorted(
        (
            # friendship_id is the FriendRequest's own pk — the frontend needs
            # it (not the friend's user id) to call DELETE and remove them.
            {
                **_user_summary(fr.other(request.user)),
                'friendship_id': fr.pk,
                'unread_messages': unread.get(fr.other(request.user).pk, 0),
                # True when they accepted a request you sent and you haven't
                # opened Friends since (#37).
                'is_new': fr.sender_id == request.user.pk and fr.response_seen_at is None,
            }
            for fr in accepted
        ),
        key=lambda item: (item['first_name'] or item['email'] or '', item['last_name']),
    )
    return JsonResponse({
        'friends': friends,
        'received_requests': [_request_payload(fr, request.user) for fr in received],
        'sent_requests': [_request_payload(fr, request.user) for fr in sent],
    })


@require_http_methods(['POST'])
def friends_seen_view(request):
    # The Friends page calls this once it has shown newly accepted requests,
    # so they stop counting as new (#37).
    if not request.user.is_authenticated:
        return _unauthorized()
    FriendRequest.objects.accepted().filter(
        sender=request.user, response_seen_at__isnull=True,
    ).update(response_seen_at=timezone.now())
    return JsonResponse({'ok': True})


@require_GET
def friend_profile_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    # #18 AC: "select a friend to view their profile." Only an actual
    # (accepted) friendship grants access — a pending or declined request
    # doesn't let either side see this. involving() + accepted() together
    # also keep this 404 (not 403) for anyone who isn't one of the two
    # parties, same privacy pattern used everywhere else in this app.
    friendship = get_object_or_404(
        FriendRequest.objects.accepted().involving(request.user), pk=pk,
    )
    return JsonResponse({'user': _user_summary(friendship.other(request.user))})


@require_http_methods(['POST'])
def friend_requests_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = SendFriendRequestForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    email = form.cleaned_data['email']

    if email == request.user.email.lower():
        return JsonResponse({'errors': {'email': ["You can't send a friend request to yourself."]}}, status=400)

    recipient = User.objects.filter(email=email).first()
    if recipient is None:
        return JsonResponse({'errors': {'email': ['No SemesterPilot account uses this email address.']}}, status=400)

    with transaction.atomic():
        # Lock both accounts, in a fixed order regardless of who's sending, so
        # two friend requests fired at each other at nearly the same instant
        # (both people click "add friend" at once) are resolved one after the
        # other instead of both slipping past the check below and leaving two
        # pending rows in opposite directions instead of one friendship.
        list(User.objects.select_for_update().filter(pk__in=sorted([request.user.pk, recipient.pk])))

        # Among any requests this pair has exchanged, only a pending or
        # accepted one is still "active" — a declined one shouldn't block
        # trying again.
        existing = next(
            (fr for fr in FriendRequest.objects.between(request.user, recipient).order_by('-created_at')
             if fr.status != FriendRequest.Status.DECLINED),
            None,
        )
        if existing is not None:
            if existing.status == FriendRequest.Status.ACCEPTED:
                return JsonResponse({'errors': {'email': ['You are already friends with this student.']}}, status=400)
            if existing.sender_id == request.user.pk:
                return JsonResponse({'errors': {'email': ['You already sent this student a friend request.']}}, status=400)
            # They already sent a pending request to us — sending one back
            # means both sides want to connect, so accept theirs instead of
            # creating a confusing duplicate that the UI would have to
            # reconcile.
            existing.accept()
            return JsonResponse({'friend_request': _request_payload(existing, request.user)})

        friend_request = FriendRequest.objects.create(sender=request.user, recipient=recipient)
    return JsonResponse({'friend_request': _request_payload(friend_request, request.user)}, status=201)


@require_http_methods(['PATCH', 'DELETE'])
def friend_request_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    with transaction.atomic():
        # Lock the row itself so a double-click (two PATCH/DELETE calls for
        # the same request landing almost simultaneously) can't both read it
        # as still-pending and both go on to act on it.
        friend_request = get_object_or_404(
            FriendRequest.objects.select_for_update().involving(request.user), pk=pk,
        )

        if request.method == 'DELETE':
            if friend_request.status == FriendRequest.Status.PENDING:
                # Canceling a request you haven't heard back on yet is a
                # sender-only action — the recipient already has PATCH
                # (accept/decline) for responding to it.
                if friend_request.sender_id != request.user.pk:
                    return JsonResponse({'detail': 'Only the sender can cancel a friend request.'}, status=403)
                friend_request.delete()
                return JsonResponse({'ok': True})
            if friend_request.status == FriendRequest.Status.ACCEPTED:
                # Removing a friend isn't directional the way sending/canceling
                # a request is — either side of an existing friendship can end
                # it. `involving()` above already guarantees request.user is
                # one of the two parties, so no extra ownership check is
                # needed. This only ever deletes this FriendRequest row — it
                # never touches either User account (deleting a friendship is
                # not deleting an account), and since this app has no message
                # model at all, there's nothing message-related to delete
                # either; a future messaging feature should key conversations
                # by the two users, not by this row, so they'd survive this
                # regardless.
                friend_request.delete()
                return JsonResponse({'ok': True})
            return JsonResponse({'detail': 'This request has already been responded to.'}, status=400)

        if friend_request.recipient_id != request.user.pk:
            return JsonResponse({'detail': 'Only the recipient can respond to a friend request.'}, status=403)
        if friend_request.status != FriendRequest.Status.PENDING:
            return JsonResponse({'detail': 'This request has already been responded to.'}, status=400)
        body = _json_body(request)
        if body is None:
            return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
        form = RespondToFriendRequestForm(body)
        if not form.is_valid():
            return JsonResponse({'errors': _errors(form)}, status=400)
        if form.cleaned_data['status'] == 'accepted':
            friend_request.accept()
        else:
            friend_request.decline()
        return JsonResponse({'friend_request': _request_payload(friend_request, request.user)})


def _shared_post_payload(message, viewer):
    # #22: the post a message shares, or None for a plain message. A post
    # that was deleted, or whose author is deactivated, is reported as
    # unavailable, matching what the feed would show.
    if not message.shares_post:
        return None
    post = message.shared_post
    if post is None or not post.author.is_active:
        return {'available': False}
    # is_saved and is_author describe the student viewing the feed, not the
    # message, so they're left out of the shared copy.
    details = {key: value for key, value in _post_payload(post, viewer).items() if key not in ('is_saved', 'is_author', 'comment_count', 'is_reported')}
    return {'available': True, **details}


def _message_payload(message, viewer):
    sender = message.sender
    return {
        'id': message.pk,
        'sender_id': message.sender_id,
        'sender_name': _display_name(sender),
        'body': message.body,
        'created_at': message.created_at.isoformat(),
        'is_mine': message.sender_id == viewer.pk,
        'shared_post': _shared_post_payload(message, viewer),
    }


@require_http_methods(['GET', 'POST'])
def conversation_view(request, pk):
    if not request.user.is_authenticated:
        return _unauthorized()
    # A matching accepted FriendRequest is required for both reading and
    # writing, including when the other person supplied a direct URL.
    friend = get_object_or_404(
        User.objects.exclude(pk=request.user.pk),
        pk=pk,
    )
    if not FriendRequest.objects.accepted().between(request.user, friend).exists():
        return JsonResponse({'detail': 'Conversation not found.'}, status=404)

    if request.method == 'GET':
        # Opening the conversation is what reads it (#37). This happens even
        # with message alerts turned off, so turning them back on doesn't
        # bring back a pile of old "unread" messages.
        DirectMessage.objects.filter(
            sender=friend, recipient=request.user, read_at__isnull=True,
        ).update(read_at=timezone.now())
        conversation = (
            DirectMessage.objects.filter(
                models.Q(sender=request.user, recipient=friend) |
                models.Q(sender=friend, recipient=request.user)
            ).select_related('sender', 'shared_post__author').order_by('created_at', 'pk')
        )
        return JsonResponse({
            'friend': _user_summary(friend),
            'messages': [_message_payload(message, request.user) for message in conversation],
        })

    body = _json_body(request)
    if not isinstance(body, dict) or not isinstance(body.get('body'), str):
        return JsonResponse({'errors': {'body': ['Enter a valid message.']}}, status=400)
    form = SendDirectMessageForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    message = DirectMessage.objects.create(
        sender=request.user, recipient=friend, body=form.cleaned_data['body'],
    )
    return JsonResponse({'message': _message_payload(message, request.user)}, status=201)


@require_http_methods(['GET', 'POST'])
def food_posts_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    if request.method == 'GET':
        # Every post the community can see, newest first (#46, #47).
        posts = _community_posts(request.user)
        return JsonResponse({'posts': [_post_payload(post, request.user) for post in posts]})
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = FoodPostForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    post = form.save(commit=False)
    post.author = request.user
    post.save()
    return JsonResponse({'post': _post_payload(post, request.user)}, status=201)


@require_GET
def alerts_view(request):
    # Numbers behind the sidebar badges (#37). A student who has turned an
    # alert off just gets zero for it.
    if not request.user.is_authenticated:
        return _unauthorized()
    # Friends alerts cover requests waiting for you, and requests you sent
    # that were accepted since you last opened Friends. Declines never alert.
    friend_requests = 0
    if request.user.friend_request_alerts_enabled:
        friend_requests = (
            FriendRequest.objects.pending().filter(recipient=request.user).count()
            + FriendRequest.objects.accepted().filter(sender=request.user, response_seen_at__isnull=True).count()
        )
    unread = _unread_by_friend(request.user)
    return JsonResponse({
        'friend_requests': friend_requests,
        'unread_messages': sum(unread.values()),
    })


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def food_post_view(request, pk):
    # #47: one post's full details. A post the feed wouldn't show (missing, or
    # by a deactivated account) is a 404 here too.
    # #51/#52: its author can edit or delete it. Anyone else gets the same 404
    # as a missing post, so the response never says whose post it is.
    if not request.user.is_authenticated:
        return _unauthorized()
    posts = _community_posts(request.user)
    if request.method != 'GET':
        posts = posts.filter(author=request.user)
    post = posts.filter(pk=pk).first()
    if post is None:
        return JsonResponse({'detail': 'Post not found.'}, status=404)
    if request.method == 'DELETE':
        post.delete()
        return JsonResponse({'ok': True})
    if request.method == 'PATCH':
        body = _json_body(request)
        if not isinstance(body, dict):
            return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
        # Fields left out of the request keep their current value.
        data = {field: getattr(post, field) for field in FoodPostForm.Meta.fields}
        data.update({key: value for key, value in body.items() if key in data})
        form = FoodPostForm(data, instance=post)
        if not form.is_valid():
            return JsonResponse({'errors': _errors(form)}, status=400)
        post = form.save()
    return JsonResponse({'post': _post_payload(post, request.user)})


@require_http_methods(['PUT', 'DELETE'])
def food_post_save_view(request, pk):
    # #53: PUT saves a post, DELETE unsaves it. Both are safe to repeat. Only
    # posts the community can see can be saved.
    if not request.user.is_authenticated:
        return _unauthorized()
    post = FoodPost.objects.community().filter(pk=pk).first()
    if post is None:
        return JsonResponse({'detail': 'Post not found.'}, status=404)
    if request.method == 'PUT':
        SavedPost.objects.get_or_create(user=request.user, post=post)
        return JsonResponse({'saved': True})
    SavedPost.objects.filter(user=request.user, post=post).delete()
    return JsonResponse({'saved': False})


@require_http_methods(['POST'])
def food_post_share_view(request, pk):
    # #22: share a post with a friend. It arrives as a message in your
    # conversation with them. Only posts the feed would show can be shared,
    # and only with accepted friends — anyone else is a 404, like the
    # conversation itself.
    if not request.user.is_authenticated:
        return _unauthorized()
    post = FoodPost.objects.community().select_related('author').filter(pk=pk).first()
    if post is None:
        return JsonResponse({'detail': 'Post not found.'}, status=404)
    body = _json_body(request)
    if not isinstance(body, dict):
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    if isinstance(body.get('friend_id'), bool):
        return JsonResponse({'errors': {'friend_id': ['Choose a friend to share this post with.']}}, status=400)
    if body.get('note') is not None and not isinstance(body['note'], str):
        return JsonResponse({'errors': {'note': ['Enter a valid note.']}}, status=400)
    form = ShareFoodPostForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    friend = User.objects.exclude(pk=request.user.pk).filter(pk=form.cleaned_data['friend_id']).first()
    if friend is None or not FriendRequest.objects.accepted().between(request.user, friend).exists():
        return JsonResponse({'detail': 'You can only share posts with your friends.'}, status=404)
    message = DirectMessage.objects.create(
        sender=request.user, recipient=friend, body=form.cleaned_data['note'],
        shared_post=post, shares_post=True,
    )
    return JsonResponse({'message': _message_payload(message, request.user)}, status=201)


@require_GET
def saved_food_posts_view(request):
    # #53: the student's saved posts, most recently saved first. A post by a
    # deactivated account drops out until the account is reactivated.
    if not request.user.is_authenticated:
        return _unauthorized()
    saved_at = SavedPost.objects.filter(user=request.user, post=models.OuterRef('pk'))
    posts = (
        _community_posts(request.user)
        .annotate(saved_at=models.Subquery(saved_at.values('created_at')[:1]), save_id=models.Subquery(saved_at.values('pk')[:1]))
        .filter(saved_at__isnull=False)
        .order_by('-saved_at', '-save_id')
    )
    return JsonResponse({'posts': [_post_payload(post, request.user) for post in posts]})


@require_http_methods(['GET', 'POST'])
def food_post_comments_view(request, pk):
    # #49: GET lists a post's comments, oldest first; POST adds one as the
    # logged-in student. Only posts the community can see take comments.
    if not request.user.is_authenticated:
        return _unauthorized()
    post = FoodPost.objects.community().filter(pk=pk).first()
    if post is None:
        return JsonResponse({'detail': 'Post not found.'}, status=404)
    if request.method == 'GET':
        comments = post.comments.community().with_reported(request.user).select_related('author')
        return JsonResponse({'comments': [_comment_payload(comment, request.user) for comment in comments]})
    body = _json_body(request)
    if not isinstance(body, dict):
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = PostCommentForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    comment = PostComment.objects.create(post=post, author=request.user, body=form.cleaned_data['body'])
    return JsonResponse({'comment': _comment_payload(comment, request.user)}, status=201)


def _report(request, author, **target):
    # #67: shared by post and comment reports. Reporting never changes or
    # hides the content; it only adds a report for the administrators.
    if author.pk == request.user.pk:
        return JsonResponse({'detail': 'You can’t report your own content.'}, status=400)
    body = _json_body(request)
    if not isinstance(body, dict):
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    if body.get('details') is not None and not isinstance(body['details'], str):
        return JsonResponse({'errors': {'details': ['Enter valid details.']}}, status=400)
    form = ReportContentForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    if ContentReport.objects.filter(reporter=request.user, **target).exists():
        return JsonResponse({'detail': 'You’ve already reported this.'}, status=409)
    try:
        with transaction.atomic():
            ContentReport.objects.create(
                reporter=request.user, reason=form.cleaned_data['reason'],
                details=form.cleaned_data['details'], **target,
            )
    except IntegrityError:
        # Two reports sent at the same moment: the database keeps one.
        return JsonResponse({'detail': 'You’ve already reported this.'}, status=409)
    return JsonResponse({'reported': True}, status=201)


@require_http_methods(['POST'])
def food_post_report_view(request, pk):
    # #67: report a post the feed shows.
    if not request.user.is_authenticated:
        return _unauthorized()
    post = FoodPost.objects.community().select_related('author').filter(pk=pk).first()
    if post is None:
        return JsonResponse({'detail': 'Post not found.'}, status=404)
    return _report(request, post.author, post=post)


@require_http_methods(['POST'])
def comment_report_view(request, pk):
    # #67: report a comment the post page shows (its author and the post's
    # author are both active).
    if not request.user.is_authenticated:
        return _unauthorized()
    comment = (
        PostComment.objects.community().filter(pk=pk, post__author__is_active=True)
        .select_related('author').first()
    )
    if comment is None:
        return JsonResponse({'detail': 'Comment not found.'}, status=404)
    return _report(request, comment.author, comment=comment)
