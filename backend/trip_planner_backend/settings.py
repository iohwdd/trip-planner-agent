from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import timedelta
from urllib.parse import quote

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional before dependencies are installed
    load_dotenv = None

try:
    import certifi
except ImportError:  # pragma: no cover - requests normally installs this already
    certifi = None


BASE_DIR = Path(__file__).resolve().parent.parent
RUNNING_TESTS = any("pytest" in arg or arg == "test" for arg in sys.argv)

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env", override=True)

if certifi is not None:
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.getenv("DJANGO_EMAIL_USE_SSL", "true").lower() == "true"
EMAIL_TIMEOUT = int(os.getenv("DJANGO_EMAIL_TIMEOUT_SECONDS", "15"))
DEFAULT_FROM_EMAIL = os.getenv(
    "DJANGO_DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@trip-agent.local",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "rest_framework",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "planner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "trip_planner_backend.urls"
WSGI_APPLICATION = "trip_planner_backend.wsgi.application"
ASGI_APPLICATION = "trip_planner_backend.asgi.application"

def _sqlite_database():
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


def _mysql_database():
    socket_path = os.getenv("MYSQL_UNIX_SOCKET", "").strip()
    if not socket_path and (os.getenv("MYSQL_HOST", "localhost").strip() in {"localhost", "127.0.0.1"}):
        for candidate in (
            "/tmp/mysql.sock",
            "/opt/homebrew/var/mysql/mysql.sock",
            "/usr/local/var/mysql/mysql.sock",
        ):
            if Path(candidate).exists():
                socket_path = candidate
                break

    options = {
        "charset": "utf8mb4",
    }
    if socket_path:
        options["unix_socket"] = socket_path

    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "trip_assistant"),
        "HOST": os.getenv("MYSQL_HOST", "localhost"),
        "PORT": int(os.getenv("MYSQL_PORT", "3306")),
        "USER": os.getenv("MYSQL_USER") or os.getenv("MYSQL_USERNAME", ""),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
        "OPTIONS": options,
    }


USE_MYSQL = os.getenv("USE_MYSQL", "false").lower() == "true"
DATABASES = {
    "default": _mysql_database() if USE_MYSQL else _sqlite_database(),
}


def _build_redis_location() -> str | None:
    host = os.getenv("REDIS_HOST", "localhost").strip()
    if not host:
        return None
    password = os.getenv("REDIS_PASSWORD") or ""
    port = os.getenv("REDIS_PORT", "6379")
    database = os.getenv("REDIS_DATABASE", "0")
    auth = f":{quote(password)}@" if password else ""
    return f"redis://{auth}{host}:{port}/{database}"


REDIS_LOCATION = _build_redis_location()

CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.redis.RedisCache"
            if REDIS_LOCATION
            else "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": REDIS_LOCATION or "trip-planner-local-cache",
        "TIMEOUT": int(os.getenv("TRIP_PLANNER_CACHE_TTL_SECONDS", "300")),
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "planner.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "planner.authentication.CacheTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [],
}

SIMPLE_TOKEN = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "120"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "14"))
    ),
}

TRIP_PLANNER_INLINE_JOBS = os.getenv("TRIP_PLANNER_INLINE_JOBS", "true").lower() == "true"
if "TRIP_PLANNER_INLINE_JOBS" not in os.environ and RUNNING_TESTS:
    TRIP_PLANNER_INLINE_JOBS = False
TRIP_PLANNER_JOB_TIMEOUT_SECONDS = int(
    os.getenv("TRIP_PLANNER_JOB_TIMEOUT_SECONDS", "90")
)
TRIP_PLANNER_AUTH_CODE_TTL_SECONDS = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_TTL_SECONDS", "600")
)
TRIP_PLANNER_AUTH_CODE_INTERVAL_SECONDS = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_INTERVAL_SECONDS", "60")
)
TRIP_PLANNER_AUTH_CODE_MAX_PER_WINDOW = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_MAX_PER_WINDOW", "5")
)
TRIP_PLANNER_AUTH_CODE_MAX_PER_IP_WINDOW = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_MAX_PER_IP_WINDOW", "10")
)
TRIP_PLANNER_AUTH_CODE_WINDOW_SECONDS = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_WINDOW_SECONDS", "3600")
)
TRIP_PLANNER_AUTH_CODE_MAX_VERIFY_ATTEMPTS = int(
    os.getenv("TRIP_PLANNER_AUTH_CODE_MAX_VERIFY_ATTEMPTS", "5")
)
TRIP_PLANNER_EXPOSE_DEBUG_AUTH_CODE = (
    os.getenv("TRIP_PLANNER_EXPOSE_DEBUG_AUTH_CODE", "false").lower() == "true"
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}
