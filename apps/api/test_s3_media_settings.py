"""Verify deployment media backend selection without connecting to AWS or RDS.

The subprocess imports settings with a fresh environment, since Django settings
are evaluated only once per Python process.
"""
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class ProductionMediaSettingsTests(SimpleTestCase):
    def _load_settings(self, bucket):
        env = {
            **os.environ,
            'DJANGO_DEBUG': 'False',
            'DJANGO_SECRET_KEY': 'test-secret-do-not-use-in-production',
            'DATABASE_ENGINE': 'postgresql',
            'DATABASE_NAME': 's3_config_test',
            'DATABASE_USER': 'test',
            'DATABASE_PASSWORD': 'test',
            'DATABASE_HOST': 'localhost',
            'AWS_STORAGE_BUCKET_NAME': bucket,
            'AWS_S3_REGION_NAME': 'us-east-2',
        }
        probe = """
import json
from django.conf import settings
print(json.dumps({
    'backend': settings.STORAGES['default']['BACKEND'],
    'signed': getattr(settings, 'AWS_QUERYSTRING_AUTH', None),
    'expiry': getattr(settings, 'AWS_QUERYSTRING_EXPIRE', None),
    'region': getattr(settings, 'AWS_S3_REGION_NAME', None),
}))
"""
        import json
        result = subprocess.run(
            [sys.executable, '-c', probe],
            cwd=settings.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return json.loads(result.stdout)

    def test_private_s3_media_uses_five_minute_signed_urls(self):
        config = self._load_settings('private-media-test-bucket')
        self.assertEqual(config['backend'], 'storages.backends.s3.S3Storage')
        self.assertIs(config['signed'], True)
        self.assertEqual(config['expiry'], 300)
        self.assertEqual(config['region'], 'us-east-2')

    def test_without_bucket_development_storage_is_unaffected(self):
        config = self._load_settings('')
        self.assertEqual(config['backend'], 'django.core.files.storage.FileSystemStorage')
