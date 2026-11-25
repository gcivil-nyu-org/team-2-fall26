"""Verify deployment media backend selection without connecting to AWS or RDS.

The subprocess imports settings with a fresh environment, since Django settings
are evaluated only once per Python process.
"""
import os
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

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
            # Test-only credentials: presigning is local and must not contact AWS.
            'AWS_ACCESS_KEY_ID': 'testing-access-key',
            'AWS_SECRET_ACCESS_KEY': 'testing-secret-key',
            'AWS_EC2_METADATA_DISABLED': 'true',
        }
        probe = """
import json
from django.conf import settings
from django.core.files.storage import default_storage
print(json.dumps({
    'backend': settings.STORAGES['default']['BACKEND'],
    'signed': getattr(settings, 'AWS_QUERYSTRING_AUTH', None),
    'expiry': getattr(settings, 'AWS_QUERYSTRING_EXPIRE', None),
    'region': getattr(settings, 'AWS_S3_REGION_NAME', None),
    'signature_version': getattr(settings, 'AWS_S3_SIGNATURE_VERSION', None),
    'url': default_storage.url('profile-pictures/sample.jpg')
        if settings.AWS_STORAGE_BUCKET_NAME else None,
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
        self.assertEqual(config['signature_version'], 's3v4')
        url = urlsplit(config['url'])
        params = parse_qs(url.query)
        self.assertEqual(url.scheme, 'https')
        self.assertIn('private-media-test-bucket', url.netloc)
        self.assertEqual(params['X-Amz-Algorithm'], ['AWS4-HMAC-SHA256'])
        self.assertEqual(params['X-Amz-Expires'], ['300'])
        self.assertIn('X-Amz-Signature', params)

    def test_without_bucket_development_storage_is_unaffected(self):
        config = self._load_settings('')
        self.assertEqual(config['backend'], 'django.core.files.storage.FileSystemStorage')
        self.assertIsNone(config['url'])
