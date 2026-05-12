import os
from django.core.exceptions import ImproperlyConfigured

from .base import *

# =========================
# PRODUCTION SETTINGS
# =========================

DEBUG = False

# =========================
# SECRET KEY (SAFE HANDLING)
# =========================
SECRET_KEY = os.getenv('SECRET_KEY', '')

if not SECRET_KEY:
    print("WARNING: SECRET_KEY not set in environment variables. Using fallback for initial deployment.")
    SECRET_KEY = 'temporary-key-replace-with-real-secret-key-in-production'
elif len(set(SECRET_KEY)) < 12:
    raise ImproperlyConfigured(
        "SECRET_KEY is too weak. Use a long random high-entropy key (50+ characters with variety)."
    )

# =========================
# ALLOWED HOSTS
# =========================
DEFAULT_ALLOWED_HOSTS = "boda-au.onrender.com,localhost,127.0.0.1,0.0.0.0"
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv(
        "ALLOWED_HOSTS",
        DEFAULT_ALLOWED_HOSTS
    ).split(",") if host.strip()
]

# Add wildcard for all render subdomains if needed
if os.getenv('ALLOW_ALL_RENDER_SUBDOMAINS', '').lower() in ['1', 'true', 'yes']:
    ALLOWED_HOSTS.append('*.onrender.com')

# =========================
# ROOT URL CONFIG (CRITICAL FIX)
# =========================
ROOT_URLCONF = 'bodaboda_web.urls'

# =========================
# DATABASE CONFIG
# =========================
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_NAME = os.getenv('DB_NAME', '')
DB_HOST = os.getenv('DB_HOST', '')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_PORT = os.getenv('DB_PORT', '5432')

if DATABASE_URL:
    DATABASES = {
        'default': _database_config_from_url(DATABASE_URL)
    }
elif all([DB_NAME, DB_HOST, DB_USER]):
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': int(DB_PORT),
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': {
                'connect_timeout': 10,
            }
        }
    }
else:
    print("WARNING: DATABASE_URL or PostgreSQL credentials not fully set. Using SQLite for initial deployment.")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# =========================
# MIDDLEWARE (WHITE NOISE FIX)
# =========================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =========================
# STATIC FILES (RENDER SAFE)
# =========================
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# =========================
# MEDIA FILES
# =========================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# =========================
# SECURITY SETTINGS (RENDER-SAFE)
# =========================
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Enable SSL redirect only if behind proxy (Render uses X-Forwarded-Proto)
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', '1').lower() in ['1', 'true', 'yes']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # Set to True only after domain is submitted

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = 'DENY'

# Optional: Trust Render's X-Forwarded-For header for IP addresses
TRUST_X_FORWARDED_FOR = os.getenv('TRUST_X_FORWARDED_FOR', '1').lower() in ['1', 'true', 'yes']
