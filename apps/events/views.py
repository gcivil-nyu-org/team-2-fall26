from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.paginator import Paginator
from django.db.models import Q, Exists, OuterRef
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_http_methods

from .engage import CAREER_CATEGORY
from .models import Event, EventCategory, EventFeedState, SavedEvent

EASTERN = ZoneInfo('America/New_York')


def payload(event, detail=False):
    result = {
        'is_saved': bool(getattr(event, 'is_saved', False)),
        'id': event.pk, 'title': event.title, 'source_url': event.source_url,
        'starts_at': event.starts_at.isoformat(), 'ends_at': event.ends_at.isoformat(),
        'location': event.location, 'host': event.host, 'status': event.status,
        'categories': [category.name for category in event.categories.all()],
    }
    if detail:
        result['description'] = event.description
    return result


@require_GET
def events_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    now = timezone.now()
    events = Event.objects.filter(status='confirmed', starts_at__gt=now).annotate(is_saved=Exists(SavedEvent.objects.filter(owner=request.user, event=OuterRef('pk'))))
    dates = {}
    for key in ('date_from', 'date_to'):
        value = request.GET.get(key, '')
        if value:
            try:
                dates[key] = parse_date(value)
            except ValueError:
                dates[key] = None
            if dates[key] is None or dates[key].year >= 9999:
                return JsonResponse({'detail': 'Enter valid dates in YYYY-MM-DD format.'}, status=400)
    if dates.get('date_from') and dates.get('date_to') and dates['date_from'] > dates['date_to']:
        return JsonResponse({'detail': 'End date must be on or after start date.'}, status=400)
    # Filter future starts by the selected Eastern dates.
    if 'date_from' in dates:
        events = events.filter(starts_at__gte=datetime.combine(dates['date_from'], time.min, EASTERN))
    if 'date_to' in dates:
        events = events.filter(starts_at__lt=datetime.combine(dates['date_to'] + timedelta(days=1), time.min, EASTERN))
    query = request.GET.get('q', '').strip()[:200]
    if query:
        events = events.filter(Q(title__icontains=query) | Q(description__icontains=query)
                               | Q(host__icontains=query) | Q(location__icontains=query))
    if request.GET.get('category'):
        events = events.filter(categories__name=request.GET['category'])
    if request.GET.get('career') == 'true':
        events = events.filter(categories__name=CAREER_CATEGORY)
    try:
        page_number = int(request.GET.get('page', '1'))
        if page_number < 1:
            raise ValueError
    except ValueError:
        return JsonResponse({'detail': 'Page must be a positive integer.'}, status=400)
    pages = Paginator(events.distinct().prefetch_related('categories'), 24)
    page = pages.get_page(page_number)
    state = EventFeedState.objects.filter(pk='engage').first()
    synced = state.last_success_at if state else None
    return JsonResponse({
        'events': [payload(event) for event in page],
        'count': pages.count, 'page': page.number, 'pages': pages.num_pages,
        'categories': list(EventCategory.objects.filter(event__status='confirmed', event__starts_at__gt=now)
                           .values_list('name', flat=True).distinct()),
        'last_synced_at': synced.isoformat() if synced else None,
        'stale': not synced or timezone.now() - synced > timedelta(days=1),
        'skipped_count': state.skipped_count if state else 0,
    })


@require_GET
def event_view(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    event = get_object_or_404(Event.objects.annotate(is_saved=Exists(SavedEvent.objects.filter(owner=request.user, event=OuterRef('pk')))).prefetch_related('categories'), pk=pk)
    return JsonResponse({'event': payload(event, detail=True)})


@require_http_methods(['PUT', 'DELETE'])
def save_event_view(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'DELETE':
        SavedEvent.objects.filter(owner=request.user, event=event).delete()
        return JsonResponse({'saved': False})
    if event.status != 'confirmed' or event.starts_at <= timezone.now():
        return JsonResponse({'detail': 'Only upcoming confirmed events can be saved.'}, status=400)
    SavedEvent.objects.get_or_create(owner=request.user, event=event)
    return JsonResponse({'saved': True})
