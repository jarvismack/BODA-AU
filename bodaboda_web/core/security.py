import logging
import time
import uuid
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse, HttpResponseForbidden

logger = logging.getLogger('core.security')


def get_client_ip(request: HttpRequest) -> str:
    trust_forwarded = bool(getattr(settings, 'TRUST_X_FORWARDED_FOR', False))
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if trust_forwarded and forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def rate_limit(*, key_prefix: str, limit: int, window_seconds: int):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args, **kwargs):
            ip = get_client_ip(request)
            user_id = request.user.id if request.user.is_authenticated else 'anon'
            session_key = ''
            try:
                session_key = request.session.session_key or ''
                if not session_key:
                    request.session.save()
                    session_key = request.session.session_key or ''
            except Exception:
                session_key = ''
            bucket = int(time.time() // window_seconds)
            cache_key = f'rl:{key_prefix}:{ip}:{user_id}:{session_key}:{bucket}'

            count = cache.get(cache_key, 0)
            if count >= limit:
                logger.warning(
                    'rate_limit_exceeded path=%s ip=%s user_id=%s key=%s limit=%s window=%s',
                    request.path,
                    ip,
                    user_id,
                    key_prefix,
                    limit,
                    window_seconds,
                )
                return JsonResponse({'detail': 'Too many requests. Please try again later.'}, status=429)

            cache.set(cache_key, count + 1, timeout=window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        response = self.get_response(request)
        response['X-Request-ID'] = request.request_id
        return response


class ApiRequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        started = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if request.path.startswith('/api/'):
            logger.info(
                'api_request method=%s path=%s status=%s ip=%s user_id=%s duration_ms=%s request_id=%s',
                request.method,
                request.path,
                response.status_code,
                get_client_ip(request),
                request.user.id if request.user.is_authenticated else 'anon',
                elapsed_ms,
                getattr(request, 'request_id', '-'),
            )

        return response


class AdminIPAllowlistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        allowed_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', [])
        if request.path.startswith('/admin/') and allowed_ips:
            client_ip = get_client_ip(request)
            if client_ip not in allowed_ips:
                logger.warning('admin_ip_blocked ip=%s path=%s', client_ip, request.path)
                return HttpResponseForbidden('Forbidden')
        return self.get_response(request)


class RequestIDLogFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        response = self.get_response(request)
        # Minimal, strict defaults for clickjacking/XSS mitigation.
        response.setdefault('X-Frame-Options', 'DENY')
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'same-origin')
        response.setdefault('Permissions-Policy', 'geolocation=(self), microphone=(), camera=()')
        response.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "connect-src 'self' https: wss:; frame-ancestors 'none'",
        )
        return response


class ApiExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        try:
            return self.get_response(request)
        except Exception:
            request_id = getattr(request, 'request_id', '-')
            logger.exception(
                'unhandled_exception path=%s method=%s request_id=%s',
                request.path,
                request.method,
                request_id,
            )
            if request.path.startswith('/api/') and not settings.DEBUG:
                response = JsonResponse({'detail': 'Internal server error'}, status=500)
                response['X-Request-ID'] = request_id
                return response
            raise
