"""Generate study sessions from availability, deadlines, and estimated workload (#41)."""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from apps.coursework.models import Assignment, Exam, Priority
from .models import AvailabilityBlock, ClassMeeting, StudySession
from .services import NYU_TIME, lock_study_account, preserved_sessions, replace_unlocked_sessions

STEP = timedelta(minutes=15)
MAX_SESSION = timedelta(hours=2)
MIN_SESSION = timedelta(minutes=30)
# A short gap between back-to-back sessions carved from one availability block.
BREAK = timedelta(minutes=15)
PRIORITY_ORDER = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2, '': 3}


class NoAvailability(Exception):
    pass


@dataclass
class PlanResult:
    sessions: list = field(default_factory=list)
    shortfalls: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def _ceil(moment):
    epoch = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)
    steps = -(-(moment - epoch) // STEP)
    return epoch + steps * STEP


def _floor(moment):
    epoch = datetime(2000, 1, 1, tzinfo=dt_timezone.utc)
    return epoch + ((moment - epoch) // STEP) * STEP


def _available(blocks, starts_at, ends_at):
    """Weekly Eastern availability expanded into UTC intervals inside the window."""
    intervals = []
    day = starts_at.astimezone(NYU_TIME).date() - timedelta(days=1)
    while day <= ends_at.astimezone(NYU_TIME).date():
        for block in blocks:
            if block.weekday != day.weekday():
                continue
            end_day = day + timedelta(days=1) if block.end_time == time.min else day
            start = datetime.combine(day, block.start_time, tzinfo=NYU_TIME).astimezone(dt_timezone.utc)
            end = datetime.combine(end_day, block.end_time, tzinfo=NYU_TIME).astimezone(dt_timezone.utc)
            start, end = max(start, starts_at), min(end, ends_at)
            if start < end:
                intervals.append((start, end))
        day += timedelta(days=1)
    return intervals


def _subtract(intervals, busy):
    free = []
    for start, end in sorted(intervals):
        pieces = [(start, end)]
        for busy_start, busy_end in busy:
            pieces = [
                piece
                for piece_start, piece_end in pieces
                for piece in ((piece_start, min(piece_end, busy_start)), (max(piece_start, busy_end), piece_end))
                if piece[0] < piece[1]
            ]
        free.extend(pieces)
    aligned = [(_ceil(start), _floor(end)) for start, end in sorted(free)]
    return [[start, end] for start, end in aligned if end - start >= MIN_SESSION]


def _deadline(item):
    # Exam prep has to finish before the exam starts.
    return item.starts_at if isinstance(item, Exam) else item.due_date


def _skip_reason(item, now):
    if _deadline(item) is None:
        return 'Add a deadline to include this in your plan.'
    if _deadline(item) <= now:
        return 'The deadline has passed.'
    if not item.estimated_workload:
        return 'Add an estimated workload to include this in your plan.'
    return None


def _session_for(item, starts_at, ends_at):
    field = 'exam' if isinstance(item, Exam) else 'assignment'
    return StudySession(**{field: item}, starts_at=starts_at, ends_at=ends_at)


def _allocate(item, needed, free, break_after=BREAK):
    deadline = _floor(_deadline(item))
    sessions = []
    for interval in free:
        if needed <= timedelta(0):
            break
        start, end = interval
        usable_end = min(end, deadline)
        while needed > timedelta(0) and usable_end - start >= min(MIN_SESSION, needed):
            length = min(MAX_SESSION, needed, usable_end - start)
            sessions.append(_session_for(item, start, start + length))
            needed -= length
            start = start + length + break_after
        interval[0] = min(start, end)
    return sessions, needed


def generate_study_plan(user, now=None):
    """Replace unlocked upcoming sessions with a plan for outstanding assignments and upcoming exams.

    Items are planned soonest deadline first (an exam's deadline is its start),
    then by priority, each filling the earliest free time before it is due.
    Locked, past, and edge-crossing sessions are kept and count toward their
    item's workload. Work that doesn't fit is reported rather than dropped.
    """
    now = now or timezone.now()
    starts_at = _ceil(now)
    result = PlanResult()
    with transaction.atomic():
        lock_study_account(user)
        blocks = list(AvailabilityBlock.objects.filter(owner=user))
        if not blocks:
            raise NoAvailability
        items = []
        candidates = list(Assignment.objects.owned_by(user).outstanding().select_related('course'))
        # Past exams are simply done; only upcoming ones need preparing for.
        candidates += Exam.objects.owned_by(user).filter(starts_at__gt=starts_at).select_related('course')
        for item in candidates:
            reason = _skip_reason(item, starts_at)
            if reason:
                result.skipped.append((item, reason))
            else:
                items.append(item)
        if not items:
            return result
        items.sort(key=lambda item: (_deadline(item), PRIORITY_ORDER.get(item.priority, 3), item.title, isinstance(item, Exam), item.pk))
        ends_at = max(_deadline(item) for item in items)

        kept = list(preserved_sessions(user, starts_at, ends_at))
        classes = ClassMeeting.objects.filter(course__owner=user, starts_at__lt=ends_at, ends_at__gt=starts_at)
        busy = [(item.starts_at, item.ends_at) for item in kept]
        busy += [(item.starts_at, item.ends_at) for item in classes]
        free = _subtract(_available(blocks, starts_at, ends_at), busy)

        planned = []
        for item in items:
            # Only kept time before the deadline helps; later sessions stay on the calendar but don't count.
            deadline = _deadline(item)
            already = sum((max(min(session.ends_at, deadline) - session.starts_at, timedelta(0))
                           for session in kept if session.item == item), timedelta(0))
            needed = timedelta(hours=float(item.estimated_workload)) - already
            # Plan in whole 15-minute steps so sessions line up on the calendar.
            needed = -(-needed // STEP) * STEP if needed > timedelta(0) else timedelta(0)
            sessions, missing = _allocate(item, needed, free)
            planned += sessions
            if missing > timedelta(0):
                result.shortfalls.append((item, missing))
        result.sessions = replace_unlocked_sessions(user, starts_at, ends_at, planned)
    return result
