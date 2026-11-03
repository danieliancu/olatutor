import os

from .base import *  # noqa: F403

DEBUG = True
INK_PROTOTYPE_ENABLED = True

_extra_hosts = os.environ.get("DJANGO_EXTRA_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", *filter(None, _extra_hosts.split(","))]
