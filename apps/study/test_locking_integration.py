"""Verify the public session API and real generator work together for #42."""
import json
from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from apps.coursework.models import Assignment, Exam
from .models import AvailabilityBlock, StudySession
from .test_generation import NOW, eastern
from .tests import StudyTestCase


class LockingIntegrationTests(StudyTestCase):
    def setUp(self):
        super().setUp()
        self.assignment.mark_complete()
        for weekday in (0, 1, 2):
            AvailabilityBlock.objects.create(owner=self.user, weekday=weekday, start_time=time(9), end_time=time(13))

    def generate(self):
        with patch('apps.study.planner.timezone.now', return_value=NOW):
            return self.client.post(reverse('study:generate'))

    def lifecycle(self, item, field):
        self.assertEqual(self.generate().status_code, 200)
        original = StudySession.objects.get(**{field: item}, starts_at=eastern('2026-11-09T09:00'))
        url = reverse('study:session', args=[original.pk])

        def update(body):
            return self.client.patch(url, json.dumps(body), content_type='application/json')

        self.assertEqual(update({'is_locked': True}).status_code, 200)
        locked_times = (original.starts_at, original.ends_at)
        self.assertEqual(self.generate().status_code, 200)
        original.refresh_from_db()
        self.assertTrue(original.is_locked)
        self.assertEqual((original.starts_at, original.ends_at), locked_times)

        # A manual move does not unlock the session, and generation respects it.
        duration = original.ends_at - original.starts_at
        new_start = eastern('2026-11-11T09:00')
        moved = update({'starts_at': new_start.isoformat(), 'ends_at': (new_start + duration).isoformat()})
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(self.generate().status_code, 200)
        original.refresh_from_db()
        self.assertTrue(original.is_locked)
        self.assertEqual(original.starts_at, new_start)
        entries = self.client.get(reverse('study:calendar'), {'week': NOW.date().isoformat()}).json()['sessions']
        visible = next(entry for entry in entries if entry['id'] == original.pk)
        self.assertTrue(visible['is_locked'])

        # The target becomes eligible for replacement only after explicit unlock.
        self.assertEqual(update({'is_locked': False}).status_code, 200)
        self.assertEqual(self.generate().status_code, 200)
        self.assertFalse(StudySession.objects.filter(pk=original.pk).exists())
        replacement = StudySession.objects.filter(**{field: item})
        self.assertTrue(replacement.exists())
        self.assertFalse(replacement.filter(is_locked=True).exists())
        self.assertFalse(replacement.filter(starts_at=new_start).exists())

    def test_assignment_lock_regenerate_reschedule_unlock_lifecycle(self):
        item = Assignment.objects.create(course=self.course, title='Integration assignment', due_date=eastern('2026-11-11T23:59'), estimated_workload=Decimal('3'))
        self.lifecycle(item, 'assignment')

    def test_exam_lock_regenerate_reschedule_unlock_lifecycle(self):
        item = Exam.objects.create(course=self.course, title='Integration exam', starts_at=eastern('2026-11-11T23:59'), estimated_workload=Decimal('3'))
        self.lifecycle(item, 'exam')
