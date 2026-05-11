from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = SECRET_KEY or 'dev-local-only-change-this'  # noqa: F405

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',  # noqa: F405
    }
}

SERVE_STATIC_INSECURE = True
SERVE_MEDIA_INSECURE = True
