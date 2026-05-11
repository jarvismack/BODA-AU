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

            bucket = int(time.time() // window_seconds)
            cache_key = f'rl:{key_prefix}:{ip}:{user_id}:{bucket}'

            count = cache.get(cache_key, 0)

            if count >= limit:
                logger.warning(
                    "rate_limit_exceeded path=%s ip=%s user_id=%s",
                    request.path, ip, user_id
                )
                return JsonResponse({'detail': 'Too many requests'}, status=429)

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
        start = time.monotonic()
        response = self.get_response(request)
        duration = int((time.monotonic() - start) * 1000)

        if request.path.startswith('/api/'):
            logger.info(
                "api_request %s %s %s %sms",
                request.method,
                request.path,
                response.status_code,
                duration,
            )

        return response


class AdminIPAllowlistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        allowed_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', [])

        if request.path.startswith('/admin/') and allowed_ips:
            ip = get_client_ip(request)

            if ip not in allowed_ips:
                logger.warning("admin_block ip=%s", ip)
                return HttpResponseForbidden("Forbidden")

        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        response = self.get_response(request)

        response.setdefault('X-Frame-Options', 'DENY')
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'same-origin')

        return response


class ApiExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        try:
            return self.get_response(request)
        except Exception:
            logger.exception("Unhandled error path=%s", request.path)

            if request.path.startswith('/api/') and not settings.DEBUG:
                return JsonResponse(
                    {'detail': 'Internal server error'},
                    status=500
                )

            raise