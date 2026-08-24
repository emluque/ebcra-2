import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = [
    "estadisticasbcra.com",
    "www.estadisticasbcra.com",
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "ebcra.middleware.JWTMiddleware",
]

ROOT_URLCONF = "ebcra.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "portal.context_processors.site_globals",
            ],
        },
    },
]

WSGI_APPLICATION = "ebcra.wsgi.application"

USE_I18N = False
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# SSL redirect is handled by nginx; Django must not redirect or it loops behind the proxy
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "formatters": {
        "simple": {
            "format": "{levelname} {name} {message}",
            "style": "{",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# External services
JWT_SERVICE_HOST = os.environ.get("JWT_SERVICE_HOST", "")
JWT_SERVICE_JS_PATH = os.environ.get("JWT_SERVICE_JS_PATH", "")
VARIATIONS_SERVICE_HOST = os.environ.get("VARIATIONS_SERVICE_HOST", "")

GOOGLE_ANALYTICS_ID = os.environ.get("GOOGLE_ANALYTICS_ID", "UA-68418371-1")
CHART_API_SCHEME = os.environ.get("CHART_API_SCHEME", "https")
CHART_API_HOST = os.environ.get("CHART_API_HOST", "api.estadisticasbcra.com")
SITE_URL = os.environ.get("SITE_URL", "https://estadisticasbcra.com")
