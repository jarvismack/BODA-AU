from __future__ import annotations

from typing import Any
import ipaddress
from functools import lru_cache

from django.conf import settings
from django.http import HttpRequest

from .models import VisitEvent
from .security import get_client_ip


def _parse_user_agent(user_agent: str) -> dict[str, str]:
    ua = (user_agent or '').lower()
    device_type = 'desktop'
    if any(token in ua for token in ('mobile', 'android', 'iphone', 'ipad')):
        device_type = 'mobile' if 'ipad' not in ua else 'tablet'
    if 'ipad' in ua or 'tablet' in ua:
        device_type = 'tablet'

    os_name = 'Unknown'
    if 'android' in ua:
        os_name = 'Android'
    elif 'iphone' in ua or 'ipad' in ua or 'ios' in ua:
        os_name = 'iOS'
    elif 'windows' in ua:
        os_name = 'Windows'
    elif 'mac os' in ua or 'macintosh' in ua:
        os_name = 'macOS'
    elif 'linux' in ua:
        os_name = 'Linux'

    browser_name = 'Unknown'
    if 'edg' in ua:
        browser_name = 'Edge'
    elif 'chrome' in ua and 'chromium' not in ua:
        browser_name = 'Chrome'
    elif 'safari' in ua and 'chrome' not in ua:
        browser_name = 'Safari'
    elif 'firefox' in ua:
        browser_name = 'Firefox'

    return {
        'device_type': device_type,
        'os_name': os_name,
        'browser_name': browser_name,
    }


@lru_cache(maxsize=1)
def _geoip_readers():
    try:
        import geoip2.database  # type: ignore
    except Exception:
        return None, None

    city_db = getattr(settings, 'GEOIP_CITY_DB', '') or ''
    asn_db = getattr(settings, 'GEOIP_ASN_DB', '') or ''
    city_reader = geoip2.database.Reader(city_db) if city_db else None
    asn_reader = geoip2.database.Reader(asn_db) if asn_db else None
    return city_reader, asn_reader


def _geoip_lookup(ip_address: str) -> dict[str, Any]:
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local:
            return {}
    except ValueError:
        return {}

    city_reader, asn_reader = _geoip_readers()
    data: dict[str, Any] = {}

    if city_reader:
        try:
            city = city_reader.city(ip_address)
            data.update(
                {
                    'country_code': (city.country.iso_code or '')[:4],
                    'country_name': (city.country.name or '')[:64],
                    'region_name': (city.subdivisions.most_specific.name or '')[:64],
                    'city_name': (city.city.name or '')[:64],
                    'timezone': (city.location.time_zone or '')[:64],
                    'latitude': city.location.latitude,
                    'longitude': city.location.longitude,
                }
            )
        except Exception:
            pass

    if asn_reader:
        try:
            asn = asn_reader.asn(ip_address)
            data.update(
                {
                    'asn': str(asn.autonomous_system_number or '')[:32],
                    'isp': (asn.autonomous_system_organization or '')[:120],
                }
            )
        except Exception:
            pass

    return data


def log_event(
    request: HttpRequest,
    *,
    event_type: str,
    user=None,
    status_code: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not getattr(settings, 'MONITORING_ENABLED', True):
        return

    ua = request.META.get('HTTP_USER_AGENT', '')[:255]
    referrer = request.META.get('HTTP_REFERER', '')[:255]
    agent_data = _parse_user_agent(ua)
    session_key = ''
    try:
        session_key = request.session.session_key or ''
    except Exception:
        session_key = ''

    geo = _geoip_lookup(get_client_ip(request))
    VisitEvent.objects.create(
        user=user if user and getattr(user, 'is_authenticated', False) else None,
        session_key=session_key,
        event_type=event_type,
        path=request.path[:180],
        method=request.method[:10],
        status_code=status_code,
        ip_address=get_client_ip(request),
        user_agent=ua,
        device_type=agent_data['device_type'],
        os_name=agent_data['os_name'],
        browser_name=agent_data['browser_name'],
        country_code=geo.get('country_code', ''),
        country_name=geo.get('country_name', ''),
        region_name=geo.get('region_name', ''),
        city_name=geo.get('city_name', ''),
        latitude=geo.get('latitude'),
        longitude=geo.get('longitude'),
        timezone=geo.get('timezone', ''),
        asn=geo.get('asn', ''),
        isp=geo.get('isp', ''),
        referrer=referrer,
        metadata=metadata or {},
    )


class MonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        response = self.get_response(request)

        if not getattr(settings, 'MONITORING_ENABLED', True):
            return response

        path = request.path or ''
        if path.startswith('/static/') or path.startswith('/media/') or path in {'/favicon.ico', '/robots.txt'}:
            return response

        event_type = None
        if request.method == 'GET' and not path.startswith('/api/'):
            event_type = VisitEvent.EventType.PAGE_VIEW
        elif request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and path.startswith('/api/'):
            event_type = VisitEvent.EventType.ACTION

        if event_type:
            try:
                log_event(
                    request,
                    event_type=event_type,
                    user=request.user if getattr(request, 'user', None) else None,
                    status_code=getattr(response, 'status_code', None),
                )
            except Exception:
                # Monitoring must never break requests.
                pass

        return response
