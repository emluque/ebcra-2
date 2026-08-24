import os  # noqa: F401 (needed for overrides below)
from .base import *  # noqa: F401, F403

DEBUG = True
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "estadisticasbcra.com", "www.estadisticasbcra.com"]

JWT_SERVICE_HOST = os.environ.get("JWT_SERVICE_HOST", "http://localhost:9001")
JWT_SERVICE_JS_PATH = os.environ.get("JWT_SERVICE_JS_PATH", "/get-js-jwt")
VARIATIONS_SERVICE_HOST = os.environ.get("VARIATIONS_SERVICE_HOST", "http://localhost:9002")
