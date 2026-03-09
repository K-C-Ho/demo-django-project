"""
Production settings for Django project.
"""
import os
from .base import *

DEBUG = False

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# AWS S3 Storage Configuration
# Install: pip install django-storages boto3
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv('AWS_STORAGE_BUCKET_NAME'),
            "region_name": os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
            "access_key": os.getenv('AWS_ACCESS_KEY_ID'),
            "secret_key": os.getenv('AWS_SECRET_ACCESS_KEY'),
            "custom_domain": os.getenv('AWS_S3_CUSTOM_DOMAIN'),  # Optional: CloudFront domain
            "location": "media",  # Folder in bucket for uploads
            "file_overwrite": False,
            "default_acl": "private",
            "querystring_auth": True,  # Signed URLs for private files
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Optional: Use S3 for static files too
# STORAGES["staticfiles"] = {
#     "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
#     "OPTIONS": {
#         "bucket_name": os.getenv('AWS_STORAGE_BUCKET_NAME'),
#         "location": "static",
#     },
# }

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True