from datetime import time
from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase


MIGRATION = '0003_remove_availabilityblock_availability_positive_duration_and_more'


class AvailabilityMigrationTests(TestCase):
    def test_utc_blocks_keep_their_duration_and_shift_to_the_correct_weekday(self):
        # Use the historical model and run the actual data operation. The
        # preceding schema operation already permits midnight endpoints.
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state([('study', MIGRATION)]).apps
        blocks = apps.get_model('study', 'AvailabilityBlock').objects
        convert = import_module(f'apps.study.migrations.{MIGRATION}').convert_availability
        cases = [
            (time(23), time(0), [(0, time(18), time(19))]),
            (time(4), time(0), [(0, time(0), time(19)), (6, time(23), time(0))]),
            (time(14), time(16), [(0, time(9), time(11))]),
            (time(4), time(5), [(6, time(23), time(0))]),
        ]
        owners = []
        for index, (start, end, _) in enumerate(cases):
            email = f'migration-{index}@nyu.edu'
            owner = get_user_model().objects.create_user(username=email, email=email)
            owners.append(owner)
            blocks.create(owner_id=owner.pk, weekday=0, start_time=start, end_time=end)

        convert(apps, connection.schema_editor())

        for owner, (start, end, expected) in zip(owners, cases):
            with self.subTest(start=start, end=end):
                actual = blocks.filter(owner_id=owner.pk).values_list('weekday', 'start_time', 'end_time')
                self.assertEqual(list(actual), expected)
