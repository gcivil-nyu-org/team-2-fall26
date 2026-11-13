"""Study-session writes shared by the calendar and future schedule generator."""
from datetime import datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AvailabilityBlock, StudySession

NYU_TIME = ZoneInfo('America/New_York')


def lock_study_account(user):
    # Availability replacement, session editing, and generation share this lock.
    get_user_model().objects.select_for_update().get(pk=user.pk)


def reschedule_warnings(user, session, starts_at, ends_at):
    warnings = []
    if StudySession.objects.owned_by(user).filter(starts_at__lt=ends_at,
                                                  ends_at__gt=starts_at).exclude(pk=session.pk).exists():
        warnings.append('This time overlaps another study session.')
    blocks = list(AvailabilityBlock.objects.filter(owner=user))
    cursor = starts_at.astimezone(dt_timezone.utc)
    end = ends_at.astimezone(dt_timezone.utc)
    while cursor < end:
        day = cursor.astimezone(NYU_TIME).date()
        ends = []
        for block in blocks:
            if block.weekday != day.weekday():
                continue
            end_day = day + timedelta(days=1) if block.end_time == time.min else day
            block_start = datetime.combine(day, block.start_time, tzinfo=NYU_TIME).astimezone(dt_timezone.utc)
            block_end = datetime.combine(end_day, block.end_time, tzinfo=NYU_TIME).astimezone(dt_timezone.utc)
            if block_start <= cursor < block_end:
                ends.append(block_end)
        covered_until = max(ends, default=None)
        if covered_until is None:
            warnings.append('This time falls outside your weekly availability.')
            break
        cursor = min(covered_until, end)
    return warnings


def session_item_payload(session):
    """The assignment or exam a session studies for, and its course."""
    course = session.course
    return {
        'assignment': {'id': session.assignment_id, 'title': session.assignment.title} if session.assignment_id else None,
        'exam': {'id': session.exam_id, 'title': session.exam.title} if session.exam_id else None,
        'course': {'id': course.pk, 'name': course.name, 'code': course.code},
    }


def preserved_sessions(user, starts_at, ends_at):
    """Return the owner's sessions that regeneration must keep unchanged.

    Only unlocked sessions wholly inside the window can be replaced. Locked
    sessions, sessions crossing either edge, and sessions outside are preserved.
    A generator should read this queryset under lock_study_account() inside the
    same transaction as planning and replacement to avoid concurrent edits.
    """
    if ends_at <= starts_at:
        raise ValidationError('The planning window must have a positive duration.')
    return StudySession.objects.owned_by(user).exclude(
        is_locked=False, starts_at__gte=starts_at, ends_at__lte=ends_at,
    ).with_course()


@transaction.atomic
def replace_unlocked_sessions(user, starts_at, ends_at, candidates):
    """#41 integration: atomically replace unlocked sessions in a planning window.

    The generator must plan around existing locked sessions and pass unsaved
    StudySession instances here. Invalid plans leave the old schedule intact.
    This does not implement the workload allocation algorithm in #41.
    """
    lock_study_account(user)
    preserved = list(preserved_sessions(user, starts_at, ends_at))
    candidates = list(candidates)
    replaceable = StudySession.objects.owned_by(user).exclude(
        pk__in=[session.pk for session in preserved],
    )
    planned = []
    for session in candidates:
        if session.pk or session.is_locked or session.course.owner_id != user.pk:
            raise ValidationError('Generated sessions must be new, unlocked, and owned by this account.')
        session.full_clean()
        if session.starts_at < starts_at or session.ends_at > ends_at:
            raise ValidationError('Generated sessions must fit inside the planning window.')
        if any(session.starts_at < other.ends_at and session.ends_at > other.starts_at for other in preserved + planned):
            raise ValidationError('Generated sessions cannot overlap preserved sessions or each other.')
        planned.append(session)
    replaceable.delete()
    return StudySession.objects.bulk_create(planned)
