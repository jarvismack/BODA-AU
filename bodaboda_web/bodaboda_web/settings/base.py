import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env_file():
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name: str, default: str = '') -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


DEBUG = _env_bool('DEBUG', False)

SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured('SECRET_KEY must be configured in production (set DEBUG=false)')

ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', 'https://boda-au.onrender.com')
NGROK_DOMAIN = os.getenv('NGROK_DOMAIN', '').strip()
if NGROK_DOMAIN and NGROK_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(NGROK_DOMAIN)
if _env_bool('ALLOW_NGROK_SUBDOMAINS', False) and '.ngrok-free.dev' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.ngrok-free.dev')
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be configured when DEBUG is false')

CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS', '')
ADMIN_ALLOWED_IPS = _env_list('ADMIN_ALLOWED_IPS', '')
MONITORING_ENABLED = _env_bool('MONITORING_ENABLED', True)
GEOIP_CITY_DB = os.getenv('GEOIP_CITY_DB', '').strip()
GEOIP_ASN_DB = os.getenv('GEOIP_ASN_DB', '').strip()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bodaboda_web.urls'
WSGI_APPLICATION = 'bodaboda_web.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'core' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
SERVE_STATIC_INSECURE = _env_bool('SERVE_STATIC_INSECURE', DEBUG)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
SERVE_MEDIA_INSECURE = _env_bool('SERVE_MEDIA_INSECURE', DEBUG)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email (OTP + password reset)
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', True)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@bodaboda.local')

# Upload limits and safe content settings.
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', str(2 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', str(8 * 1024 * 1024)))
MAX_PROFILE_IMAGE_BYTES = int(os.getenv('MAX_PROFILE_IMAGE_BYTES', str(2 * 1024 * 1024)))

# Cache used for in-app rate limiting.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'bodaboda-security-cache',
    }
}

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

USE_X_FORWARDED_HOST = _env_bool('USE_X_FORWARDED_HOST', False)
TRUST_X_FORWARDED_FOR = _env_bool('TRUST_X_FORWARDED_FOR', False)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('CSRF_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', False)

AXES_FAILURE_LIMIT = int(os.getenv('AXES_FAILURE_LIMIT', '5'))
AXES_COOLOFF_TIME = float(os.getenv('AXES_COOLOFF_TIME', '1'))
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ['ip_address', 'username']
AXES_IPWARE_META_PRECEDENCE_ORDER = [
    'HTTP_X_FORWARDED_FOR',
    'REMOTE_ADDR',
]

# Application-level rate-limit defaults.
RATE_LIMIT_BURST_PER_MINUTE = int(os.getenv('RATE_LIMIT_BURST_PER_MINUTE', '60'))
RATE_LIMIT_LOGIN_PER_5_MIN = int(os.getenv('RATE_LIMIT_LOGIN_PER_5_MIN', '15'))
RATE_LIMIT_REGISTER_PER_HOUR = int(os.getenv('RATE_LIMIT_REGISTER_PER_HOUR', '30'))
SCHEDULED_MATCH_LEAD_MINUTES = int(os.getenv('SCHEDULED_MATCH_LEAD_MINUTES', '15'))
SCHEDULED_MATCH_RETRY_MINUTES = int(os.getenv('SCHEDULED_MATCH_RETRY_MINUTES', '5'))
SCHEDULED_MIN_LEAD_MINUTES = int(os.getenv('SCHEDULED_MIN_LEAD_MINUTES', '10'))

SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'console')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER', '')

APP_VERSION_CODE = int(os.getenv('APP_VERSION_CODE', '1'))
APP_VERSION_NAME = os.getenv('APP_VERSION_NAME', '1.0').strip()
APP_APK_URL = os.getenv('APP_APK_URL', '').strip()
BACKUP_DIR = Path(os.getenv('BACKUP_DIR', str(BASE_DIR / 'backups')))
PUSH_PROVIDER = os.getenv('PUSH_PROVIDER', 'native').strip().lower()
PUSH_POLL_INTERVAL_SECONDS = int(os.getenv('PUSH_POLL_INTERVAL_SECONDS', '60'))
FCM_SERVER_KEY = os.getenv('FCM_SERVER_KEY', '').strip()
FCM_SERVICE_ACCOUNT_FILE = os.getenv('FCM_SERVICE_ACCOUNT_FILE', '').strip()
FCM_SERVICE_ACCOUNT_JSON = os.getenv('FCM_SERVICE_ACCOUNT_JSON', '').strip()
FCM_PROJECT_ID = os.getenv('FCM_PROJECT_ID', '').strip()

CLAMAV_ENABLED = _env_bool('CLAMAV_ENABLED', False)
CLAMAV_HOST = os.getenv('CLAMAV_HOST', '127.0.0.1')
CLAMAV_PORT = int(os.getenv('CLAMAV_PORT', '3310'))

NOMINATIM_BASE_URL = os.getenv('NOMINATIM_BASE_URL', 'https://nominatim.openstreetmap.org/search')
NOMINATIM_TIMEOUT_SECONDS = int(os.getenv('NOMINATIM_TIMEOUT_SECONDS', '6'))

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'structured': {
            'format': '%(asctime)s level=%(levelname)s logger=%(name)s request_id=%(request_id)s message=%(message)s',
        },
    },
    'filters': {
        'request_id': {
            '()': 'core.security.RequestIDLogFilter',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'structured',
            'filters': ['request_id'],
        },
    },
    'loggers': {
        '': {'handlers': ['console'], 'level': LOG_LEVEL},
        'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'core.security': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

DATABASE_CONN_MAX_AGE = int(os.getenv('DB_CONN_MAX_AGE', '0' if DEBUG else '60'))
