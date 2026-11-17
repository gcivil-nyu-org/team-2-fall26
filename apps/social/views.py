import json

from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User

from .forms import FoodPostForm, RespondToFriendRequestForm, SendDirectMessageForm, SendFriendRequestForm
from .models import DirectMessage, FoodPost, FriendRequest


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


def _user_summary(user):
    return {
        'id': user.pk,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'bio': user.bio,
        # Lets the frontend show a real photo on friend requests and in the
        # friends list (falling back to an initial when there isn't one) —
        # same shape apps/api/views.py's _user_payload already uses for a
        # user's own profile.
        'profile_picture': user.profile_picture.url if user.profile_picture else None,
    }


def _request_payload(friend_request, viewer):
    return {
        'id': friend_request.pk,
        'status': friend_request.status,
        'direction': 'sent' if friend_request.sender_id == viewer.pk else 'received',
        'user': _user_summary(friend_request.other(viewer)),
        'created_at': friend_request.created_at.isoformat(),
    }


def _post_payload(post):
    return {
        'id': post.pk,
        'place_name': post.place_name,
        'description': post.description,
        'location': post.location,
        'cuisine': post.cuisine,
        'rating': post.rating,
        # The feed shows every student's posts, but bios are friends-only
        # (#35), so the author summary here leaves the bio out.
        'author': {k: v for k, v in _user_summary(post.author).items() if k != 'bio'},
        'created_at': post.created_at.isoformat(),
    }


@require_GET
def friends_view(request):
    if not request.user.is_authenticated:
        return _unauthorized()
    accepted = FriendRequest.objects.accepted().involving(request.user).select_related('sender', 'recipient')
    received = FriendRequest.objects.pending().filter(recipient=request.user).select_related('sender')
    sent = FriendRequest.objects.pending().filter(sender=request.user).select_related('recipient')
    friends = sorted(
        (
            # friendship_id is the FriendRequest's own pk — the frontend needs
            # it (not the friend's user id) to call DELETE and remove them.
            {**_user_summary(fr.other(request.user)), 'friendship_id': fr.pk}
            for fr in accepted
        ),
        key=lambda item: (item['first_name'] or item['email'], item['last_name']),
    )
    return JsonResponse({
        'friends': friends,
        'received_requests': [_request_payload(fr, request.user) for fr in received],
        'sent_requests': [_request_payload(fr, request.user) for fr in sent],
    })


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


def _message_payload(message, viewer):
    sender = message.sender
    return {
        'id': message.pk,
        'sender_id': message.sender_id,
        'sender_name': ' '.join(filter(None, [sender.first_name, sender.last_name])) or sender.email,
        'body': message.body,
        'created_at': message.created_at.isoformat(),
        'is_mine': message.sender_id == viewer.pk,
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
        conversation = (
            DirectMessage.objects.filter(
                models.Q(sender=request.user, recipient=friend) |
                models.Q(sender=friend, recipient=request.user)
            ).select_related('sender').order_by('created_at', 'pk')
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
        # #46 AC: a submitted post appears in the community feed. This is
        # every student's posts, newest first; browsing and filtering the
        # feed is #47.
        posts = FoodPost.objects.select_related('author')
        return JsonResponse({'posts': [_post_payload(post) for post in posts]})
    body = _json_body(request)
    if body is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    form = FoodPostForm(body)
    if not form.is_valid():
        return JsonResponse({'errors': _errors(form)}, status=400)
    post = form.save(commit=False)
    post.author = request.user
    post.save()
    return JsonResponse({'post': _post_payload(post)}, status=201)
