import json
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import transaction
from django import forms
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.coursework.models import Course

from .albert import parse_calendar
from .forms import AvailabilityBlockForm
from .models import AvailabilityBlock, ClassMeeting, StudySession
from .services import NYU_TIME, lock_study_account, reschedule_warnings


@require_POST
def albert_import_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    try:
        term, events = parse_calendar(request.FILES.get('calendar'))
    except UnicodeError:
        return JsonResponse({'detail': 'The calendar could not be read. Download a fresh .ics export from Albert.'}, status=400)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)

    meetings = ClassMeeting.objects.filter(course__owner=request.user, term=term)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        courses = {str(course.pk): course for course in request.user.courses.filter(semester__iexact=term)}
        previous = dict(meetings.values_list('source_uid', 'course_id').distinct())
        if request.POST.get('confirm') != 'yes':
            rows = []
            for uid, event in events.items():
                matches = [key for key, course in courses.items()
                           if ' '.join(course.name.casefold().split()) == ' '.join(event['title'].casefold().split())]
                saved = str(previous.get(uid))
                selected = saved if saved in courses else matches[0] if len(matches) == 1 else 'new' if not courses else ''
                rows.append({'uid': uid, 'title': event['title'], 'selected': selected})
            return JsonResponse({
                'term': term, 'classes': rows,
                'courses': [{'id': key, 'name': course.name, 'code': course.code} for key, course in courses.items()],
                'replacing': bool(previous),
            })

        choices = {uid: request.POST.get(f'course:{uid}') for uid in events}
        if any(choice != 'new' and choice not in courses for choice in choices.values()):
            return JsonResponse({'detail': 'Choose a course for every class and try again.'}, status=400)
        created = {}
        rows = []
        for uid, event in events.items():
            choice = choices[uid]
            if choice == 'new':
                key = ' '.join(event['title'].casefold().split())
                if key not in created:
                    matches = [course for course in courses.values() if ' '.join(course.name.casefold().split()) == key]
                    if len(matches) == 1:
                        created[key] = matches[0]
                    else:
                        created[key] = Course.objects.create(owner=request.user, semester=term, name=event['title'])
                course = created[key]
            else:
                course = courses[choice]
            rows.extend(ClassMeeting(course=course, term=term, source_uid=uid, starts_at=start,
                                     ends_at=end, location=event['location']) for start, end in event['times'])
        meetings.delete()
        ClassMeeting.objects.bulk_create(rows)
    return JsonResponse({'meetings': len(rows), 'term': term})


def _availability_payload(user):
    blocks = list(user.availability_blocks.all())
    return {
        'timezone': NYU_TIME.key,
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
                    and (previous.cleaned_data['end_time'] == time.min
                         or form.cleaned_data['start_time'] < previous.cleaned_data['end_time'])):
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
        selected = date.fromisoformat(request.GET['week']) if 'week' in request.GET else timezone.now().astimezone(NYU_TIME).date()
        # Keep navigation and the exclusive end within representable dates.
        if not date(1900, 1, 8) <= selected <= date(9998, 12, 20):
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'detail': 'Choose a week using a valid date (YYYY-MM-DD).'}, status=400)
    monday = selected - timedelta(days=selected.weekday())
    end = monday + timedelta(days=7)
    start_at = datetime.combine(monday, time.min, tzinfo=NYU_TIME)
    end_at = datetime.combine(end, time.min, tzinfo=NYU_TIME)
    sessions = StudySession.objects.filter(
        assignment__course__owner=request.user, starts_at__lt=end_at, ends_at__gt=start_at,
    ).select_related('assignment__course')
    classes = ClassMeeting.objects.filter(
        course__owner=request.user, starts_at__lt=end_at, ends_at__gt=start_at,
    ).select_related('course')
    return JsonResponse({
        'timezone': NYU_TIME.key,
        'week_start': monday.isoformat(),
        'week_end': end.isoformat(),
        'previous_week': (monday - timedelta(days=7)).isoformat(),
        'next_week': end.isoformat(),
        'availability_configured': AvailabilityBlock.objects.filter(owner=request.user).exists(),
        'classes': [
            {'id': f'class-{meeting.pk}', 'starts_at': meeting.starts_at.isoformat(),
             'ends_at': meeting.ends_at.isoformat(), 'location': meeting.location,
             'course': {'id': meeting.course_id, 'name': meeting.course.name, 'code': meeting.course.code}}
            for meeting in classes
        ],
        'sessions': [
            {
                'id': session.pk,
                'is_locked': session.is_locked,
                'starts_at': session.starts_at.astimezone(dt_timezone.utc).isoformat(),
                'ends_at': session.ends_at.astimezone(dt_timezone.utc).isoformat(),
                'assignment': {'id': session.assignment_id, 'title': session.assignment.title},
                'course': {'id': session.assignment.course_id, 'name': session.assignment.course.name, 'code': session.assignment.course.code},
            }
            for session in sessions
        ],
    })


class SessionTimeForm(forms.Form):
    starts_at = forms.DateTimeField()
    ends_at = forms.DateTimeField()

    def clean(self):
        values = super().clean()
        start, end = values.get('starts_at'), values.get('ends_at')
        if start and end:
            if end.astimezone(dt_timezone.utc) <= start.astimezone(dt_timezone.utc):
                self.add_error('ends_at', 'The session must end after it starts.')
            elif not date(1900, 1, 8) <= start.date() <= end.date() <= date(9998, 12, 20):
                self.add_error('starts_at', 'Choose dates between 1900 and 9998.')
        return values


@require_http_methods(['PATCH'])
def session_view(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'Send a JSON object.'}, status=400)
    if not isinstance(body, dict) or not body or set(body) - {'is_locked', 'starts_at', 'ends_at', 'confirm_warnings'}:
        return JsonResponse({'detail': 'Send only lock or reschedule fields.'}, status=400)
    for field in ('is_locked', 'confirm_warnings'):
        if field in body and type(body[field]) is not bool:
            return JsonResponse({'errors': {field: ['Enter true or false.']}}, status=400)
    moving = 'starts_at' in body or 'ends_at' in body
    if not moving and 'is_locked' not in body:
        return JsonResponse({'detail': 'Choose a lock state or a new time.'}, status=400)
    form = None
    if moving:
        for field in ('starts_at', 'ends_at'):
            if field in body and not isinstance(body[field], str):
                return JsonResponse({'errors': {field: ['Enter a valid date and time.']}}, status=400)
        with timezone.override(NYU_TIME):
            form = SessionTimeForm(body)
            if not form.is_valid():
                return JsonResponse({'errors': {key: list(value) for key, value in form.errors.items()}}, status=400)
    with transaction.atomic():
        lock_study_account(request.user)
        session = get_object_or_404(StudySession.objects.select_for_update(), pk=session_id,
                                    assignment__course__owner=request.user)
        if moving:
            start, end = form.cleaned_data['starts_at'], form.cleaned_data['ends_at']
            warnings = reschedule_warnings(request.user, session, start, end)
            if warnings and not body.get('confirm_warnings', False):
                return JsonResponse({'detail': 'Review these warnings before moving the session.', 'warnings': warnings}, status=409)
            session.starts_at, session.ends_at = start, end
        if 'is_locked' in body:
            session.is_locked = body['is_locked']
        session.save(update_fields=['starts_at', 'ends_at', 'is_locked'])
    return JsonResponse({'id': session.pk, 'is_locked': session.is_locked,
                         'starts_at': session.starts_at.astimezone(dt_timezone.utc).isoformat(),
                         'ends_at': session.ends_at.astimezone(dt_timezone.utc).isoformat()})
