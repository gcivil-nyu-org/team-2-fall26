import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import User

from .forms import RespondToFriendRequestForm, SendFriendRequestForm
from .models import FriendRequest


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
    }


def _request_payload(friend_request, viewer):
    return {
        'id': friend_request.pk,
        'status': friend_request.status,
        'direction': 'sent' if friend_request.sender_id == viewer.pk else 'received',
        'user': _user_summary(friend_request.other(viewer)),
        'created_at': friend_request.created_at.isoformat(),
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
