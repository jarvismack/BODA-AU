from .base import *  # noqa: F403

DEBUG = False

if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY must be set')  # noqa: F405
if len(set(SECRET_KEY)) < 12:
    raise ImproperlyConfigured('SECRET_KEY is too weak. Use a long random secret with high entropy.')  # noqa: F405

DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')  # noqa: F405
DB_NAME = os.getenv('DB_NAME')  # noqa: F405
if not DB_NAME:
    raise ImproperlyConfigured('DB_NAME must be set for production')  # noqa: F405

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': DB_NAME,
        'USER': os.getenv('DB_USER', ''),  # noqa: F405
        'PASSWORD': os.getenv('DB_PASSWORD', ''),  # noqa: F405
        'HOST': os.getenv('DB_HOST', ''),  # noqa: F405
        'PORT': os.getenv('DB_PORT', '5432'),  # noqa: F405
        'CONN_MAX_AGE': DATABASE_CONN_MAX_AGE,  # noqa: F405
    }
}

MIDDLEWARE = [  # noqa: F405
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *MIDDLEWARE,  # noqa: F405
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

SERVE_STATIC_INSECURE = False
SERVE_MEDIA_INSECURE = False
