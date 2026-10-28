import json
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .forms import AvailabilityBlockForm
from .models import AvailabilityBlock, StudySession


def _availability_payload(user):
    blocks = list(user.availability_blocks.all())
    return {
        'timezone': 'UTC',
        'configured': bool(blocks),
        'blocks': [
            {'weekday': block.weekday, 'start_time': block.start_time.strftime('%H:%M'), 'end_time': block.end_time.strftime('%H:%M')}
            for block in blocks
        ],
    }


@require_http_methods(['GET', 'PUT'])
def availability_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    if request.method == 'GET':
        return JsonResponse(_availability_payload(request.user))
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'Send a JSON object containing a blocks list.'}, status=400)
    if not isinstance(body, dict) or not isinstance(body.get('blocks'), list):
        return JsonResponse({'detail': 'Send a JSON object containing a blocks list.'}, status=400)
    forms, errors = [], {}
    for index, block in enumerate(body['blocks']):
        if not isinstance(block, dict):
            errors[str(index)] = {'__all__': ['Each time block must be an object.']}
            continue
        field_errors = {}
        if 'weekday' in block and (type(block['weekday']) is not int):
            field_errors['weekday'] = ['Choose a weekday from Monday (0) to Sunday (6).']
        for field in ('start_time', 'end_time'):
            if field in block and not isinstance(block[field], str):
                field_errors[field] = ['Enter a time in HH:MM format.']
        if field_errors:
            errors[str(index)] = field_errors
            continue
        form = AvailabilityBlockForm(block)
        if not form.is_valid():
            errors[str(index)] = {key: list(messages) for key, messages in form.errors.items()}
        forms.append((index, form))
    if not errors:
        ordered = sorted(forms, key=lambda item: (item[1].cleaned_data['weekday'], item[1].cleaned_data['start_time']))
        for (_, previous), (index, form) in zip(ordered, ordered[1:]):
            if (form.cleaned_data['weekday'] == previous.cleaned_data['weekday']
                    and form.cleaned_data['start_time'] < previous.cleaned_data['end_time']):
                errors[str(index)] = {'start_time': ['Time blocks on the same day cannot overlap.']}
    if errors:
        return JsonResponse({'detail': 'Check the highlighted time blocks.', 'errors': errors}, status=400)
    with transaction.atomic():
        # Serialize whole-week replacements for this account, including its
        # first save when there are no availability rows to lock yet.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        request.user.availability_blocks.all().delete()
        AvailabilityBlock.objects.bulk_create([
            AvailabilityBlock(owner=request.user, **form.cleaned_data) for _, form in forms
        ])
    return JsonResponse(_availability_payload(request.user))


@require_GET
def calendar_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    try:
        selected = date.fromisoformat(request.GET['week']) if 'week' in request.GET else timezone.now().astimezone(dt_timezone.utc).date()
        # Keep navigation and the exclusive end within representable dates.
        if not date(1900, 1, 8) <= selected <= date(9998, 12, 20):
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'detail': 'Choose a week using a valid date (YYYY-MM-DD).'}, status=400)
    monday = selected - timedelta(days=selected.weekday())
    end = monday + timedelta(days=7)
    start_at = datetime.combine(monday, time.min, tzinfo=dt_timezone.utc)
    end_at = datetime.combine(end, time.min, tzinfo=dt_timezone.utc)
    sessions = StudySession.objects.filter(
        assignment__course__owner=request.user, starts_at__lt=end_at, ends_at__gt=start_at,
    ).select_related('assignment__course')
    return JsonResponse({
        'timezone': 'UTC',
        'week_start': monday.isoformat(),
        'week_end': end.isoformat(),
        'previous_week': (monday - timedelta(days=7)).isoformat(),
        'next_week': end.isoformat(),
        'availability_configured': AvailabilityBlock.objects.filter(owner=request.user).exists(),
        'sessions': [
            {
                'id': session.pk,
                'starts_at': session.starts_at.astimezone(dt_timezone.utc).isoformat(),
                'ends_at': session.ends_at.astimezone(dt_timezone.utc).isoformat(),
                'assignment': {'id': session.assignment_id, 'title': session.assignment.title},
                'course': {'id': session.assignment.course_id, 'name': session.assignment.course.name, 'code': session.assignment.course.code},
            }
            for session in sessions
        ],
    })
