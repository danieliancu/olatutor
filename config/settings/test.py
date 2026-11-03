import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret")
os.environ.setdefault("DATABASE_PASSWORD", "unset")

from .base import *  # noqa: E402, F403

ALLOWED_HOSTS = ["testserver", "localhost"]
INK_PROTOTYPE_ENABLED = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
