"""Study-session writes shared by the calendar and future schedule generator."""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AvailabilityBlock, StudySession


def lock_study_account(user):
    # Availability replacement, session editing, and generation share this lock.
    get_user_model().objects.select_for_update().get(pk=user.pk)


def reschedule_warnings(user, session, starts_at, ends_at):
    warnings = []
    if StudySession.objects.filter(assignment__course__owner=user, starts_at__lt=ends_at,
                                   ends_at__gt=starts_at).exclude(pk=session.pk).exists():
        warnings.append('This time overlaps another study session.')
    blocks = list(AvailabilityBlock.objects.filter(owner=user))
    cursor = starts_at.astimezone(dt_timezone.utc)
    end = ends_at.astimezone(dt_timezone.utc)
    while cursor < end:
        covered_until = max((datetime.combine(cursor.date(), block.end_time, tzinfo=dt_timezone.utc)
                             for block in blocks if block.weekday == cursor.weekday()
                             and block.start_time <= cursor.time().replace(tzinfo=None) < block.end_time),
                            default=None)
        if covered_until is None:
            warnings.append('This time falls outside your weekly availability.')
            break
        cursor = min(covered_until, end)
    return warnings


@transaction.atomic
def replace_unlocked_sessions(user, starts_at, ends_at, candidates):
    """#41 integration: atomically replace unlocked sessions in a planning window.

    The generator must plan around existing locked sessions and pass unsaved
    StudySession instances here. Invalid plans leave the old schedule intact.
    This does not implement the workload allocation algorithm in #41.
    """
    lock_study_account(user)
    if ends_at <= starts_at:
        raise ValidationError('The planning window must have a positive duration.')
    candidates = list(candidates)
    existing = StudySession.objects.filter(assignment__course__owner=user)
    replaceable = existing.filter(is_locked=False, starts_at__gte=starts_at, ends_at__lte=ends_at)
    preserved = list(existing.exclude(pk__in=replaceable.values('pk')))
    planned = []
    for session in candidates:
        if session.pk or session.is_locked or session.assignment.course.owner_id != user.pk:
            raise ValidationError('Generated sessions must be new, unlocked, and owned by this account.')
        session.full_clean()
        if session.starts_at < starts_at or session.ends_at > ends_at:
            raise ValidationError('Generated sessions must fit inside the planning window.')
        if any(session.starts_at < other.ends_at and session.ends_at > other.starts_at for other in preserved + planned):
            raise ValidationError('Generated sessions cannot overlap preserved sessions or each other.')
        planned.append(session)
    replaceable.delete()
    return StudySession.objects.bulk_create(planned)
