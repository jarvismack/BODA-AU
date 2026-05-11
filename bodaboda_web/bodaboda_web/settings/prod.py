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
SECRET_KEY = os.getenv('SECRET_KEY')

if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY is missing in environment variables")

if len(set(SECRET_KEY)) < 12:
    raise ImproperlyConfigured(
        "SECRET_KEY is too weak. Use a long random high-entropy key."
    )

# =========================
# ALLOWED HOSTS
# =========================
ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "boda-au.onrender.com,localhost,127.0.0.1"
).split(",")

# =========================
# ROOT URL CONFIG (CRITICAL FIX)
# =========================
ROOT_URLCONF = 'bodaboda_web.urls'

# =========================
# DATABASE CONFIG
# =========================
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_NAME = os.getenv('DB_NAME')

if not DB_NAME:
    raise ImproperlyConfigured("DB_NAME must be set for production")

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': DB_NAME,
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
    }
}

# =========================
# MIDDLEWARE (WHITE NOISE FIX)
# =========================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *MIDDLEWARE,
]

# =========================
# STATIC FILES (RENDER SAFE)
# =========================
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# =========================
# MEDIA FILES
# =========================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# =========================
# SECURITY SETTINGS
# =========================
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = 'DENY'

# =========================
# OPTIONAL SAFE DEFAULTS
# =========================
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')