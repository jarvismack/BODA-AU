import json
import socket
from pathlib import Path
from urllib import parse, request as urlrequest
import logging
import re
import random
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import connection
from django.db import transaction
from django.db.models import Count, Sum, F
from django.utils import timezone
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from PIL import Image

from .models import (
    ACTIVE_ZANZIBAR_LOCATIONS,
    AppNotification,
    ChatMessage,
    DriverLedgerEntry,
    DriverProfile,
    DriverDocument,
    EmergencyAlert,
    EmergencyContact,
    IdempotencyKey,
    NotificationLog,
    PromoCode,
    PushDeviceToken,
    Ride,
    RideStop,
    RideRating,
    SystemSetting,
    UserProfile,
    VisitEvent,
    Location,
    StationRequest,
    haversine_km,
    closest_active_location,
    get_active_locations,
)
from .monitoring import log_event
from .security import get_client_ip, rate_limit
from .services import create_app_notification, send_sms_notification, send_whatsapp_otp, send_email_otp

logger = logging.getLogger('core.security')
PHONE_PATTERN = re.compile(r'^\+?[0-9][0-9\-\s]{8,19}$')
ALLOWED_IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
LANGUAGE_CHOICES = {'en', 'sw'}


def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return {}


def _role(user: User) -> str:
    if user.is_superuser:
        return UserProfile.Role.ADMIN
    profile = getattr(user, 'profile', None)
    if not profile:
        return UserProfile.Role.PASSENGER
    return profile.role


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'detail': 'Authentication required'}, status=401)
            if _role(request.user) not in roles:
                return JsonResponse({'detail': 'Forbidden'}, status=403)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def _driver_payload(driver: DriverProfile) -> dict:
    return {
        'driver_id': driver.user_id,
        'name': driver.user.first_name or driver.user.username,
        'phone_number': getattr(getattr(driver.user, 'profile', None), 'phone_number', ''),
        'vehicle_type': driver.vehicle_type,
        'license_number': driver.license_number,
        'plate_number': driver.plate_number,
        'profile_image_url': _absolute_media_url(None, driver.profile_image),
        'is_verified': driver.is_verified,
        'is_online': driver.is_online,
    }


def _ride_stops_payload(ride: Ride) -> list[dict]:
    stops = ride.stops.all() if hasattr(ride, 'stops') else []
    return [
        {
            'name': stop.name,
            'latitude': float(stop.latitude),
            'longitude': float(stop.longitude),
            'order': stop.stop_order,
        }
        for stop in stops
    ]


def _database_health_snapshot() -> dict:
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return {
            'status': 'ok',
            'database': 'ok',
            'error': '',
        }
    except Exception:  # noqa: BLE001
        return {
            'status': 'degraded',
            'database': 'unavailable',
            'error': 'Database check failed',
        }


def _backup_health_snapshot() -> dict:
    backup_dir = Path(getattr(settings, 'BACKUP_DIR', Path(settings.BASE_DIR) / 'backups'))
    snapshot = {
        'backup_dir': str(backup_dir),
        'exists': backup_dir.exists(),
        'count': 0,
        'latest_backup_name': '',
        'latest_backup_at': '',
        'latest_backup_size_bytes': 0,
    }
    if not backup_dir.exists():
        return snapshot

    files = [path for path in backup_dir.iterdir() if path.is_file()]
    snapshot['count'] = len(files)
    if not files:
        return snapshot

    latest = max(files, key=lambda path: path.stat().st_mtime)
    latest_stat = latest.stat()
    snapshot.update(
        {
            'latest_backup_name': latest.name,
            'latest_backup_at': datetime.fromtimestamp(latest_stat.st_mtime, tz=timezone.get_current_timezone()).isoformat(),
            'latest_backup_size_bytes': latest_stat.st_size,
        }
    )
    return snapshot


def _risk_flag_for_user(user: User, role: str) -> str:
    window_start = timezone.now() - timedelta(days=30)
    if role == UserProfile.Role.DRIVER:
        cancelled = Ride.objects.filter(driver=user, status=Ride.RideStatus.CANCELLED, created_at__gte=window_start).count()
    else:
        cancelled = Ride.objects.filter(passenger=user, status=Ride.RideStatus.CANCELLED, created_at__gte=window_start).count()
    if cancelled >= 3:
        return 'High'
    if cancelled == 2:
        return 'Medium'
    return 'Low'


def _passenger_payload(profile: UserProfile) -> dict:
    return {
        'passenger_id': profile.user_id,
        'name': profile.user.first_name or profile.user.username,
        'phone_number': profile.phone_number,
        'profile_image_url': _absolute_media_url(None, profile.profile_image),
        'is_active': profile.user.is_active,
    }


def _absolute_media_url(request: HttpRequest | None, file_field) -> str | None:
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    if request is None:
        return url
    return request.build_absolute_uri(url)


def _passenger_details(user: User, request: HttpRequest) -> dict:
    profile = getattr(user, 'profile', None)
    return {
        'id': user.id,
        'name': user.first_name or user.username,
        'email': user.email or '',
        'phone_number': getattr(profile, 'phone_number', ''),
        'profile_image_url': _absolute_media_url(request, getattr(profile, 'profile_image', None)),
        'language': getattr(profile, 'language', 'en') if profile else 'en',
    }


def _driver_details(user: User | None, request: HttpRequest) -> dict | None:
    if not user:
        return None
    profile = getattr(user, 'profile', None)
    driver_profile = getattr(user, 'driver_profile', None)
    return {
        'id': user.id,
        'name': user.first_name or user.username,
        'email': user.email or '',
        'phone_number': getattr(profile, 'phone_number', ''),
        'station_name': getattr(profile, 'driver_station_name', ''),
        'station_verified': getattr(profile, 'driver_station_verified', False),
        'vehicle_type': getattr(driver_profile, 'vehicle_type', None),
        'plate_number': getattr(driver_profile, 'plate_number', ''),
        'license_number': getattr(driver_profile, 'license_number', ''),
        'profile_image_url': _absolute_media_url(request, getattr(driver_profile, 'profile_image', None)),
        'latitude': float(driver_profile.latitude) if getattr(driver_profile, 'latitude', None) is not None else None,
        'longitude': float(driver_profile.longitude) if getattr(driver_profile, 'longitude', None) is not None else None,
        'language': getattr(profile, 'language', 'en') if profile else 'en',
    }


DEFAULT_SETTINGS = {
    'service_radius_km': '3',
    'price_per_km_tzs': '700',
    'base_fare_motorcycle_tzs': '1500',
    'base_fare_bajaji_tzs': '2500',
    'driver_debt_limit_tzs': '3000',
    'commission_band_short_max_tzs': '2000',
    'commission_fee_short_tzs': '100',
    'commission_band_medium_max_tzs': '4000',
    'commission_fee_medium_tzs': '200',
    'commission_band_long_max_tzs': '6500',
    'commission_fee_long_tzs': '300',
    'commission_fee_extended_tzs': '500',
    'driver_settlement_provider': 'M-Pesa',
    'driver_settlement_phone': '+255787104836',
    'driver_settlement_reference_prefix': 'BODAAU',
    'weather_advisory_enabled': 'true',
    'weather_rain_probability_pct': '45',
    'weather_rain_mm_threshold': '0.2',
    'weather_lookahead_hours': '3',
    'surge_enabled': 'false',
    'surge_multiplier': '1.00',
    'first_ride_discount_pct': '10',
}


def _read_setting(key: str) -> str:
    setting = SystemSetting.objects.filter(key=key).first()
    return setting.value if setting else DEFAULT_SETTINGS[key]


def _read_setting_decimal(key: str) -> Decimal:
    try:
        return Decimal(_read_setting(key))
    except InvalidOperation:
        return Decimal(DEFAULT_SETTINGS[key])


def _read_setting_float(key: str) -> float:
    try:
        return float(_read_setting(key))
    except ValueError:
        return float(DEFAULT_SETTINGS[key])


def _read_setting_int(key: str) -> int:
    try:
        return int(Decimal(_read_setting(key)))
    except (InvalidOperation, ValueError):
        return int(Decimal(DEFAULT_SETTINGS[key]))


def _setting_enabled(key: str) -> bool:
    return str(_read_setting(key)).strip().lower() in {'1', 'true', 'yes', 'on'}


def _calculate_fare_by_settings(vehicle_type: str, distance_km: Decimal) -> Decimal:
    price_per_km = _read_setting_decimal('price_per_km_tzs')
    motorcycle_base = _read_setting_decimal('base_fare_motorcycle_tzs')
    bajaji_base = _read_setting_decimal('base_fare_bajaji_tzs')
    base = motorcycle_base if vehicle_type == DriverProfile.VehicleType.MOTORCYCLE else bajaji_base
    return base + (distance_km * price_per_km)


def _driver_commission_for_fare(fare_tzs: Decimal) -> Decimal:
    short_max = _read_setting_decimal('commission_band_short_max_tzs')
    medium_max = _read_setting_decimal('commission_band_medium_max_tzs')
    long_max = _read_setting_decimal('commission_band_long_max_tzs')
    if fare_tzs <= short_max:
        return _read_setting_decimal('commission_fee_short_tzs')
    if fare_tzs <= medium_max:
        return _read_setting_decimal('commission_fee_medium_tzs')
    if fare_tzs <= long_max:
        return _read_setting_decimal('commission_fee_long_tzs')
    return _read_setting_decimal('commission_fee_extended_tzs')


def _driver_outstanding_balance(driver_profile: DriverProfile) -> Decimal:
    total = driver_profile.ledger_entries.aggregate(total=Sum('amount_tzs'))['total']
    return total or Decimal('0')


def _driver_debt_limit() -> Decimal:
    return _read_setting_decimal('driver_debt_limit_tzs')


def _driver_commission_summary(driver_profile: DriverProfile) -> dict:
    outstanding = _driver_outstanding_balance(driver_profile)
    debt_limit = _driver_debt_limit()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_fees = (
        driver_profile.ledger_entries.filter(entry_type=DriverLedgerEntry.EntryType.COMMISSION, created_at__gte=today_start)
        .aggregate(total=Sum('amount_tzs'))['total']
        or Decimal('0')
    )
    total_commission = (
        driver_profile.ledger_entries.filter(entry_type=DriverLedgerEntry.EntryType.COMMISSION).aggregate(total=Sum('amount_tzs'))['total']
        or Decimal('0')
    )
    total_settled = (
        driver_profile.ledger_entries.filter(entry_type=DriverLedgerEntry.EntryType.SETTLEMENT).aggregate(total=Sum('amount_tzs'))['total']
        or Decimal('0')
    )
    recent_entries = driver_profile.ledger_entries.select_related('ride')[:6]
    return {
        'outstanding_balance_tzs': str(outstanding),
        'debt_limit_tzs': str(debt_limit),
        'is_over_limit': outstanding >= debt_limit,
        'today_fees_tzs': str(today_fees),
        'total_commission_tzs': str(total_commission),
        'total_settled_tzs': str(abs(total_settled)),
        'entries': [
            {
                'id': entry.id,
                'entry_type': entry.entry_type,
                'amount_tzs': str(entry.amount_tzs),
                'ride_id': entry.ride_id,
                'note': entry.note,
                'created_at': entry.created_at.isoformat(),
            }
            for entry in recent_entries
        ],
    }


def _driver_settlement_instructions(driver_profile: DriverProfile) -> dict:
    reference_prefix = _read_setting('driver_settlement_reference_prefix')
    reference = f'{reference_prefix}-{driver_profile.user_id}'
    return {
        'provider': _read_setting('driver_settlement_provider'),
        'phone_number': _read_setting('driver_settlement_phone'),
        'reference': reference,
        'note': f'Use reference {reference} when sending your weekly settlement.',
    }


WEATHER_CODE_LABELS = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    61: 'Slight rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    71: 'Slight snow fall',
    80: 'Rain showers',
    81: 'Moderate rain showers',
    82: 'Violent rain showers',
    95: 'Thunderstorm',
}


def _weather_label(code: int | None) -> str:
    if code is None:
        return 'Unknown'
    return WEATHER_CODE_LABELS.get(code, 'Changing weather')


def _calculate_fare_breakdown(*, passenger: User, vehicle_type: str, distance_km: Decimal, promo_code: str | None) -> dict:
    base_fare = _read_setting_decimal('base_fare_motorcycle_tzs') if vehicle_type == DriverProfile.VehicleType.MOTORCYCLE else _read_setting_decimal('base_fare_bajaji_tzs')
    price_per_km = _read_setting_decimal('price_per_km_tzs')
    raw_fare = base_fare + (distance_km * price_per_km)

    surge_multiplier = Decimal('1.00')
    if _setting_enabled('surge_enabled'):
        try:
            surge_multiplier = Decimal(_read_setting('surge_multiplier'))
        except InvalidOperation:
            surge_multiplier = Decimal('1.00')
    surged_fare = raw_fare * surge_multiplier

    first_ride_discount_pct = Decimal('0')
    completed_count = Ride.objects.filter(passenger=passenger, status=Ride.RideStatus.COMPLETED).count()
    if completed_count == 0:
        try:
            first_ride_discount_pct = Decimal(_read_setting('first_ride_discount_pct'))
        except InvalidOperation:
            first_ride_discount_pct = Decimal('0')

    promo_discount_pct = Decimal('0')
    promo_applied_code = ''
    if promo_code:
        promo = PromoCode.objects.filter(code__iexact=promo_code.strip(), is_active=True).first()
        if promo and (promo.expires_at is None or promo.expires_at > timezone.now()) and promo.used_count < promo.max_uses:
            promo_discount_pct = promo.discount_pct
            promo_applied_code = promo.code

    total_discount_pct = min(Decimal('80'), first_ride_discount_pct + promo_discount_pct)
    discount_amount = (surged_fare * total_discount_pct) / Decimal('100')
    final_fare = max(Decimal('0'), surged_fare - discount_amount)

    return {
        'base_fare': base_fare,
        'price_per_km': price_per_km,
        'raw_fare': raw_fare,
        'surge_multiplier': surge_multiplier,
        'surged_fare': surged_fare,
        'first_ride_discount_pct': first_ride_discount_pct,
        'promo_code': promo_applied_code,
        'promo_discount_pct': promo_discount_pct,
        'discount_amount': discount_amount,
        'final_fare': final_fare,
    }


def vehicle_label(vehicle_type: str) -> str:
    return 'Bajaji' if vehicle_type == DriverProfile.VehicleType.BAJAJI else 'Bodaboda'


def _validate_phone_number(phone_number: str) -> bool:
    return bool(PHONE_PATTERN.match(phone_number))


def _validate_password_strength(password: str) -> bool:
    if len(password) < 8:
        return False
    has_alpha = any(char.isalpha() for char in password)
    has_digit = any(char.isdigit() for char in password)
    return has_alpha and has_digit


def _valid_coordinate_pair(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _active_ride_for_user(user: User):
    active_statuses = [Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED]
    role = _role(user)
    if role == UserProfile.Role.PASSENGER:
        return (
            Ride.objects.filter(passenger=user, status__in=active_statuses)
            .order_by('-created_at')
            .first()
        )
    if role == UserProfile.Role.DRIVER:
        return (
            Ride.objects.filter(driver=user, status__in=active_statuses)
            .order_by('-created_at')
            .first()
        )
    return None


def _resolve_location_key(key: str) -> tuple[str, float, float] | None:
    if not key:
        return None
    for name, (lat, lng) in get_active_locations().items():
        if key.strip().lower() == name.strip().lower().replace(' ', '_'):
            return name, float(lat), float(lng)
    for name, (lat, lng) in get_active_locations().items():
        if key.strip().lower() == name.strip().lower():
            return name, float(lat), float(lng)
    return None


def _suggest_locations(query: str, limit: int = 5) -> list[str]:
    from difflib import get_close_matches

    names = list(get_active_locations().keys())
    if not query:
        return names[:limit]
    matches = get_close_matches(query, names, n=limit, cutoff=0.3)
    if matches:
        return matches
    lowered = query.lower()
    contains = [name for name in names if lowered in name.lower()]
    return contains[:limit]


def _idempotent_response(user: User, endpoint: str, request_id: str):
    if not request_id:
        return None
    entry = IdempotencyKey.objects.filter(user=user, key=request_id, endpoint=endpoint).first()
    if entry:
        return entry.response_json
    return None


def _store_idempotent_response(user: User, endpoint: str, request_id: str, payload: dict):
    if not request_id:
        return
    IdempotencyKey.objects.get_or_create(
        user=user,
        key=request_id,
        endpoint=endpoint,
        defaults={'response_json': payload},
    )


def _compute_distance_km(pickup: tuple[float, float], dropoff: tuple[float, float], stops: list[tuple[float, float]] | None) -> Decimal:
    total = 0.0
    points = [pickup] + (stops or []) + [dropoff]
    for idx in range(len(points) - 1):
        total += haversine_km(points[idx][0], points[idx][1], points[idx + 1][0], points[idx + 1][1])
    return Decimal(str(round(total, 2)))


def _apply_promo_usage(code: str):
    if not code:
        return
    PromoCode.objects.filter(code__iexact=code).update(used_count=F('used_count') + 1)


def _eligible_drivers(pickup_lat: float, pickup_lng: float, vehicle_type: str) -> list[DriverProfile]:
    drivers = DriverProfile.objects.filter(
        is_online=True, is_verified=True, vehicle_type=vehicle_type
    ).exclude(latitude__isnull=True, longitude__isnull=True)

    radius_km = _read_setting_float('service_radius_km')
    busy_driver_ids = set(
        Ride.objects.filter(
            status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED]
        ).values_list('driver_id', flat=True)
    )

    nearby = []
    for driver in drivers:
        distance = haversine_km(pickup_lat, pickup_lng, float(driver.latitude), float(driver.longitude))
        if distance <= radius_km:
            if driver.user_id not in busy_driver_ids:
                nearby.append((driver, distance))

    nearby.sort(key=lambda item: item[1])
    return [driver for driver, _distance in nearby]


def _schedule_datetime_from_parts(date_value: str, time_value: str) -> datetime | None:
    if not date_value or not time_value:
        return None
    try:
        combined = datetime.fromisoformat(f'{date_value}T{time_value}')
    except ValueError:
        return None
    if timezone.is_naive(combined):
        combined = timezone.make_aware(combined, timezone.get_current_timezone())
    return combined


def _validate_image_upload(uploaded_file):
    if not uploaded_file:
        return

    if uploaded_file.size > settings.MAX_PROFILE_IMAGE_BYTES:
        raise ValidationError('Image too large. Max size is 2MB.')

    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type and content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValidationError('Unsupported image type. Allowed: jpeg, png, webp.')

    # Verify payload is a real image and reset stream for Django storage.
    try:
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError('Invalid image file.') from exc


def _clamav_scan(uploaded_file):
    if not getattr(settings, 'CLAMAV_ENABLED', False):
        return
    host = getattr(settings, 'CLAMAV_HOST', '127.0.0.1')
    port = int(getattr(settings, 'CLAMAV_PORT', 3310))

    chunk_size = 1024 * 16
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(b'zINSTREAM\0')
        while True:
            chunk = uploaded_file.read(chunk_size)
            if not chunk:
                break
            sock.sendall(len(chunk).to_bytes(4, byteorder='big'))
            sock.sendall(chunk)
        sock.sendall((0).to_bytes(4, byteorder='big'))
        response = sock.recv(4096).decode('utf-8', errors='ignore')

    uploaded_file.seek(0)
    if 'FOUND' in response:
        raise ValidationError('Malware detected in uploaded file.')
    if 'OK' not in response:
        raise ValidationError('Virus scan failed. Please try again later.')


def index(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'auth.html')


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    profile = getattr(request.user, 'profile', None)
    driver_profile = getattr(request.user, 'driver_profile', None)
    profile_image = getattr(profile, 'profile_image', None) or getattr(driver_profile, 'profile_image', None)
    return render(
        request,
        'dashboard.html',
        {
            'role': _role(request.user),
            'name': request.user.first_name or request.user.username,
            'phone_number': getattr(getattr(request.user, 'profile', None), 'phone_number', ''),
            'profile_image_url': _absolute_media_url(request, profile_image),
            'language': getattr(profile, 'language', 'en') if profile else 'en',
        },
    )


def safety_center(request: HttpRequest) -> HttpResponse:
    return render(request, 'safety_center.html')


def help_contact(request: HttpRequest) -> HttpResponse:
    return render(request, 'help_contact.html')


def terms_privacy(request: HttpRequest) -> HttpResponse:
    return render(request, 'terms_privacy.html')


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER)
def passenger_profile_me(request: HttpRequest) -> JsonResponse:
    return JsonResponse({'profile': _passenger_details(request.user, request)})


@require_POST
@rate_limit(key_prefix='schedule_ride', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def schedule_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    vehicle_type = data.get('vehicle_type')
    if vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
        return JsonResponse({'detail': 'vehicle_type must be motorcycle or bajaji'}, status=400)
    promo_code = str(data.get('promo_code') or '').strip()
    request_id = str(data.get('request_id') or '').strip()
    cached = _idempotent_response(request.user, 'schedule_ride', request_id)
    if cached:
        return JsonResponse(cached, status=200)

    date_value = (data.get('date') or '').strip()
    time_value = (data.get('time') or '').strip()
    scheduled_for = _schedule_datetime_from_parts(date_value, time_value)
    if not scheduled_for:
        return JsonResponse({'detail': 'Valid date and time are required'}, status=400)

    min_lead = timedelta(minutes=settings.SCHEDULED_MIN_LEAD_MINUTES)
    if scheduled_for <= timezone.now() + min_lead:
        return JsonResponse({'detail': 'Scheduled time must be in the future (at least 10 minutes ahead)'}, status=400)

    try:
        pickup_lat = Decimal(str(data.get('pickup_lat')))
        pickup_lng = Decimal(str(data.get('pickup_lng')))
        dropoff_lat = Decimal(str(data.get('dropoff_lat')))
        dropoff_lng = Decimal(str(data.get('dropoff_lng')))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'Invalid coordinates or distance'}, status=400)
    if not (
        _valid_coordinate_pair(float(pickup_lat), float(pickup_lng))
        and _valid_coordinate_pair(float(dropoff_lat), float(dropoff_lng))
    ):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)

    stops_input = data.get('stops')
    if not isinstance(stops_input, list):
        stop_key = str(data.get('stop_location') or '').strip()
        stops_input = [stop_key] if stop_key else []
    if len(stops_input) > 2:
        return JsonResponse({'detail': 'Maximum 2 stops allowed'}, status=400)

    stops = []
    for raw_key in stops_input:
        key = str(raw_key or '').strip()
        if not key:
            continue
        resolved = _resolve_location_key(key)
        if not resolved:
            return JsonResponse({'detail': f'Invalid stop location: {key}'}, status=400)
        stops.append(resolved)
    stop_names = [stop[0] for stop in stops]
    if len(stop_names) != len(set(stop_names)):
        return JsonResponse({'detail': 'Stop locations must be unique'}, status=400)
    pickup_name = closest_active_location(float(pickup_lat), float(pickup_lng))
    dropoff_name = closest_active_location(float(dropoff_lat), float(dropoff_lng))
    if any(name in {pickup_name, dropoff_name} for name in stop_names):
        return JsonResponse({'detail': 'Stop locations must differ from pickup/dropoff'}, status=400)

    distance_km = _compute_distance_km(
        (float(pickup_lat), float(pickup_lng)),
        (float(dropoff_lat), float(dropoff_lng)),
        [(stop[1], stop[2]) for stop in stops],
    )
    if distance_km <= 0:
        return JsonResponse({'detail': 'distance_km must be greater than 0'}, status=400)

    existing = Ride.objects.filter(
        passenger=request.user,
        status__in=[
            Ride.RideStatus.SCHEDULED,
            Ride.RideStatus.REQUESTED,
            Ride.RideStatus.ACCEPTED,
            Ride.RideStatus.STARTED,
        ],
    ).exists()
    if existing:
        return JsonResponse({'detail': 'You already have an active or scheduled ride'}, status=400)

    breakdown = _calculate_fare_breakdown(
        passenger=request.user,
        vehicle_type=vehicle_type,
        distance_km=distance_km,
        promo_code=promo_code,
    )
    fare_tzs = breakdown['final_fare']
    ride = Ride.objects.create(
        passenger=request.user,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        distance_km=distance_km,
        fare_tzs=fare_tzs,
        status=Ride.RideStatus.SCHEDULED,
        requested_vehicle_type=vehicle_type,
        promo_code=breakdown['promo_code'],
        promo_discount_pct=breakdown['promo_discount_pct'],
        surge_multiplier=breakdown['surge_multiplier'],
        scheduled_for=scheduled_for,
    )
    _apply_promo_usage(breakdown['promo_code'])
    for idx, stop in enumerate(stops, start=1):
        RideStop.objects.create(
            ride=ride,
            name=stop[0],
            latitude=Decimal(str(stop[1])),
            longitude=Decimal(str(stop[2])),
            stop_order=idx,
        )
    response = {
        'detail': 'Ride scheduled successfully',
        'ride': {
            'id': ride.id,
            'status': ride.status,
            'scheduled_for': ride.scheduled_for.isoformat(),
            'vehicle_type': vehicle_type,
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'stop_location': stops[0][0] if stops else None,
            'stops': _ride_stops_payload(ride),
            'fare_tzs': str(ride.fare_tzs),
            'fare_breakdown': {
                'base_fare': str(breakdown['base_fare']),
                'price_per_km': str(breakdown['price_per_km']),
                'raw_fare': str(breakdown['raw_fare']),
                'surge_multiplier': str(breakdown['surge_multiplier']),
                'surged_fare': str(breakdown['surged_fare']),
                'first_ride_discount_pct': str(breakdown['first_ride_discount_pct']),
                'promo_code': breakdown['promo_code'],
                'promo_discount_pct': str(breakdown['promo_discount_pct']),
                'discount_amount': str(breakdown['discount_amount']),
                'final_fare': str(breakdown['final_fare']),
            },
        },
    }
    _store_idempotent_response(request.user, 'schedule_ride', request_id, response)
    return JsonResponse(response, status=201)


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER)
def scheduled_rides(request: HttpRequest) -> JsonResponse:
    rides = Ride.objects.filter(passenger=request.user, status=Ride.RideStatus.SCHEDULED).order_by('scheduled_for')
    payload = [
        {
            'id': ride.id,
            'status': ride.status,
            'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
            'vehicle_type': ride.requested_vehicle_type,
            'fare_tzs': str(ride.fare_tzs),
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'stops': _ride_stops_payload(ride),
        }
        for ride in rides
    ]
    return JsonResponse({'rides': payload})


@require_POST
@rate_limit(key_prefix='scheduled_cancel', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def cancel_scheduled_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)
    try:
        ride = Ride.objects.get(id=ride_id, passenger=request.user, status=Ride.RideStatus.SCHEDULED)
    except Ride.DoesNotExist:
        return JsonResponse({'detail': 'Scheduled ride not found'}, status=404)
    ride.status = Ride.RideStatus.CANCELLED
    ride.save(update_fields=['status'])
    return JsonResponse({'detail': 'Scheduled ride cancelled'})


@require_POST
@rate_limit(key_prefix='scheduled_update', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def update_scheduled_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)
    date_value = (data.get('date') or '').strip()
    time_value = (data.get('time') or '').strip()
    scheduled_for = _schedule_datetime_from_parts(date_value, time_value)
    if not scheduled_for:
        return JsonResponse({'detail': 'Valid date and time are required'}, status=400)
    min_lead = timedelta(minutes=settings.SCHEDULED_MIN_LEAD_MINUTES)
    if scheduled_for <= timezone.now() + min_lead:
        return JsonResponse({'detail': 'Scheduled time must be in the future (at least 10 minutes ahead)'}, status=400)
    try:
        ride = Ride.objects.get(id=ride_id, passenger=request.user, status=Ride.RideStatus.SCHEDULED)
    except Ride.DoesNotExist:
        return JsonResponse({'detail': 'Scheduled ride not found'}, status=404)
    ride.scheduled_for = scheduled_for
    ride.scheduled_search_started_at = None
    ride.save(update_fields=['scheduled_for', 'scheduled_search_started_at'])
    return JsonResponse({'detail': 'Scheduled ride updated', 'scheduled_for': ride.scheduled_for.isoformat()})


@require_POST
@rate_limit(key_prefix='passenger_profile_update', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def passenger_profile_update(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'profile', None)
    if profile is None:
        return JsonResponse({'detail': 'Profile not found'}, status=404)

    full_name = (request.POST.get('full_name') or '').strip()
    phone_number = (request.POST.get('phone_number') or '').strip()
    email = (request.POST.get('email') or '').strip()
    language = (request.POST.get('language') or '').strip().lower()
    profile_image = request.FILES.get('profile_image')

    if full_name:
        request.user.first_name = full_name
    if phone_number:
        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
        exists = UserProfile.objects.exclude(user_id=request.user.id).filter(phone_number=phone_number).exists()
        if exists:
            return JsonResponse({'detail': 'Phone number already exists'}, status=400)
        profile.phone_number = phone_number
        request.user.username = phone_number
    if email:
        if len(email) > 254 or '@' not in email:
            return JsonResponse({'detail': 'Invalid email address'}, status=400)
        email_exists = User.objects.exclude(id=request.user.id).filter(email=email).exists()
        if email_exists:
            return JsonResponse({'detail': 'Email is already registered'}, status=400)
        request.user.email = email
    if profile_image:
        try:
            _validate_image_upload(profile_image)
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
        profile.profile_image = profile_image
    if language:
        if language not in LANGUAGE_CHOICES:
            return JsonResponse({'detail': 'Invalid language'}, status=400)
        profile.language = language

    request.user.save()
    profile.save()
    return JsonResponse({'detail': 'Passenger profile updated', 'profile': _passenger_details(request.user, request)})


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def emergency_contacts_list(request: HttpRequest) -> JsonResponse:
    contacts = EmergencyContact.objects.filter(user=request.user, is_active=True)
    payload = [
        {
            'id': contact.id,
            'name': contact.name,
            'phone_number': contact.phone_number,
            'relationship': contact.relationship,
            'is_active': contact.is_active,
        }
        for contact in contacts
    ]
    return JsonResponse({'contacts': payload})


@require_POST
@rate_limit(key_prefix='emergency_contacts_upsert', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def emergency_contacts_upsert(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    contacts = data.get('contacts')
    if not isinstance(contacts, list):
        return JsonResponse({'detail': 'contacts list is required'}, status=400)
    if len(contacts) > 5:
        return JsonResponse({'detail': 'Maximum 5 emergency contacts are allowed'}, status=400)

    cleaned = []
    for item in contacts:
        if not isinstance(item, dict):
            return JsonResponse({'detail': 'Each contact must be an object'}, status=400)
        name = str(item.get('name') or '').strip()
        phone_number = str(item.get('phone_number') or '').strip()
        relationship = str(item.get('relationship') or '').strip()
        if not name and not phone_number:
            continue
        if not name or not phone_number:
            return JsonResponse({'detail': 'Each contact requires name and phone_number'}, status=400)
        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': f'Invalid phone number: {phone_number}'}, status=400)
        cleaned.append({'name': name[:120], 'phone_number': phone_number, 'relationship': relationship[:64]})

    EmergencyContact.objects.filter(user=request.user).delete()
    for entry in cleaned:
        EmergencyContact.objects.create(user=request.user, **entry, is_active=True)

    return JsonResponse({'detail': 'Emergency contacts saved', 'count': len(cleaned)})


@require_POST
@rate_limit(key_prefix='register', limit=settings.RATE_LIMIT_REGISTER_PER_HOUR, window_seconds=3600)
def register_view(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    full_name = (data.get('full_name') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    role = data.get('role') or UserProfile.Role.PASSENGER
    station_key = (data.get('station_key') or '').strip()
    language = (data.get('language') or '').strip().lower()

    if role not in {UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER}:
        return JsonResponse({'detail': 'Invalid role'}, status=400)
    if language and language not in LANGUAGE_CHOICES:
        return JsonResponse({'detail': 'Invalid language'}, status=400)
    if not language:
        language = 'en'

    if not _validate_password_strength(password):
        return JsonResponse({'detail': 'Password must be at least 8 characters and include letters and numbers'}, status=400)

    if not full_name or not phone_number:
        return JsonResponse({'detail': 'Full name and phone number are required'}, status=400)
    if not _validate_phone_number(phone_number):
        return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
    if not email or '@' not in email or len(email) > 254:
        return JsonResponse({'detail': 'Valid email is required'}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({'detail': 'Email is already registered'}, status=400)

    if UserProfile.objects.filter(phone_number=phone_number).exists():
        return JsonResponse({'detail': 'Phone number is already registered'}, status=400)

    username = phone_number
    user = User.objects.create_user(username=username, password=password, first_name=full_name, email=email)
    station_name = ''
    station_lat = None
    station_lng = None
    station_verified = False
    if role == UserProfile.Role.DRIVER:
        resolved = _resolve_location_key(station_key)
        if not resolved:
            suggestions = _suggest_locations(station_key)
            user.delete()
            return JsonResponse(
                {'detail': 'Station must match a known Zanzibar location', 'suggestions': suggestions},
                status=400,
            )
        station_name, station_lat, station_lng = resolved
        station_verified = True

    UserProfile.objects.create(
        user=user,
        phone_number=phone_number,
        role=role,
        language=language,
        email_verified=False,
        driver_station_name=station_name,
        driver_station_lat=station_lat,
        driver_station_lng=station_lng,
        driver_station_verified=station_verified,
    )
    if role == UserProfile.Role.PASSENGER:
        send_sms_notification(
            user=user,
            phone_number=phone_number,
            event='passenger_registration',
            message='Karibu Zanzibar Bodaboda! Your passenger account is now active.',
        )
    else:
        send_sms_notification(
            user=user,
            phone_number=phone_number,
            event='driver_registration',
            message='Karibu Zanzibar Bodaboda! Your driver account is created and pending admin verification.',
        )

    otp_code = f'{random.randint(0, 999999):06d}'
    cache.set(f'otp_email:{email}', otp_code, timeout=600)
    otp_log = send_email_otp(user=user, email=email, otp_code=otp_code)
    if otp_log.status != NotificationLog.Status.SENT:
        user.delete()
        return JsonResponse({'detail': 'Email OTP failed. Please try again.'}, status=500)

    try:
        log_event(
            request,
            event_type=VisitEvent.EventType.REGISTER,
            user=user,
            status_code=201,
            metadata={'role': role, 'phone_number': phone_number},
        )
    except Exception:
        pass

    return JsonResponse({'detail': 'Account created successfully'}, status=201)


@require_POST
@rate_limit(key_prefix='login', limit=settings.RATE_LIMIT_LOGIN_PER_5_MIN, window_seconds=300)
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        data = _json_body(request)
        phone_number = (data.get('phone_number') or '').strip()
        password = data.get('password') or ''

        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': 'Invalid phone number or password'}, status=401)

        user = authenticate(request, username=phone_number, password=password)
        if not user:
            logger.warning('login_failed phone=%s ip=%s', phone_number, get_client_ip(request))
            return JsonResponse({'detail': 'Invalid phone number or password'}, status=401)

        profile = getattr(user, 'profile', None)
        if profile and not profile.email_verified:
            return JsonResponse({'detail': 'Please verify your email before logging in'}, status=403)

        login(request, user)
        logger.info('login_success user_id=%s ip=%s', user.id, get_client_ip(request))
        try:
            log_event(request, event_type=VisitEvent.EventType.LOGIN, user=user, status_code=200)
        except Exception:
            pass
        return JsonResponse({'detail': 'Login successful'})
    except Exception:
        logger.exception('login_exception ip=%s', get_client_ip(request))
        return JsonResponse({'detail': 'Login failed. Please try again.'}, status=500)


@require_POST
@rate_limit(key_prefix='verify_email_otp', limit=10, window_seconds=600)
def verify_email_otp(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    email = (data.get('email') or '').strip()
    otp = (data.get('otp') or '').strip()
    if not email or not otp:
        return JsonResponse({'detail': 'Email and OTP are required'}, status=400)
    cached = cache.get(f'otp_email:{email}')
    if not cached or cached != otp:
        return JsonResponse({'detail': 'Invalid or expired OTP'}, status=400)
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'detail': 'User not found'}, status=404)
    profile = getattr(user, 'profile', None)
    if profile:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    cache.delete(f'otp_email:{email}')
    return JsonResponse({'detail': 'Email verified'})


@require_POST
@rate_limit(key_prefix='resend_email_otp', limit=5, window_seconds=600)
def resend_email_otp(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    email = (data.get('email') or '').strip()
    if not email:
        return JsonResponse({'detail': 'Email is required'}, status=400)
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({'detail': 'User not found'}, status=404)
    profile = getattr(user, 'profile', None)
    if profile and profile.email_verified:
        return JsonResponse({'detail': 'Email already verified'}, status=400)
    otp_code = f'{random.randint(0, 999999):06d}'
    cache.set(f'otp_email:{email}', otp_code, timeout=600)
    send_email_otp(user=user, email=email, otp_code=otp_code)
    return JsonResponse({'detail': 'OTP resent'})


@require_POST
@login_required
def logout_view(request: HttpRequest) -> JsonResponse:
    user = request.user if request.user.is_authenticated else None
    logout(request)
    if user:
        try:
            log_event(request, event_type=VisitEvent.EventType.LOGOUT, user=user, status_code=200)
        except Exception:
            pass
    return JsonResponse({'detail': 'Logged out'})


@require_GET
@rate_limit(key_prefix='nearby_drivers', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def nearby_drivers(request: HttpRequest) -> JsonResponse:
    try:
        lat = float(request.GET.get('lat', ''))
        lng = float(request.GET.get('lng', ''))
    except ValueError:
        return JsonResponse({'detail': 'lat and lng are required'}, status=400)
    if not _valid_coordinate_pair(lat, lng):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)

    vehicle_type = request.GET.get('vehicle_type')
    if vehicle_type and vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
        return JsonResponse({'detail': 'Invalid vehicle_type'}, status=400)

    drivers = DriverProfile.objects.filter(is_online=True, is_verified=True).exclude(
        latitude__isnull=True, longitude__isnull=True
    )
    if vehicle_type:
        drivers = drivers.filter(vehicle_type=vehicle_type)

    radius_km = _read_setting_float('service_radius_km')
    matches = []
    for driver in drivers:
        distance = haversine_km(lat, lng, float(driver.latitude), float(driver.longitude))
        if distance <= radius_km:
            matches.append((driver, round(distance, 3)))

    matches.sort(key=lambda item: item[1])
    payload = [
        {
            'driver_id': driver.user_id,
            'name': driver.user.first_name or driver.user.username,
            'vehicle_type': driver.vehicle_type,
            'distance_km': distance,
            'latitude': float(driver.latitude),
            'longitude': float(driver.longitude),
        }
        for driver, distance in matches
    ]
    return JsonResponse({'drivers': payload})


@require_POST
@rate_limit(key_prefix='request_ride', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def request_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    vehicle_type = data.get('vehicle_type')
    if vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
        return JsonResponse({'detail': 'vehicle_type must be motorcycle or bajaji'}, status=400)
    promo_code = str(data.get('promo_code') or '').strip()
    request_id = str(data.get('request_id') or '').strip()
    cached = _idempotent_response(request.user, 'request_ride', request_id)
    if cached:
        return JsonResponse(cached, status=200)

    try:
        pickup_lat = Decimal(str(data.get('pickup_lat')))
        pickup_lng = Decimal(str(data.get('pickup_lng')))
        dropoff_lat = Decimal(str(data.get('dropoff_lat')))
        dropoff_lng = Decimal(str(data.get('dropoff_lng')))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'Invalid coordinates or distance'}, status=400)
    if not (
        _valid_coordinate_pair(float(pickup_lat), float(pickup_lng))
        and _valid_coordinate_pair(float(dropoff_lat), float(dropoff_lng))
    ):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)

    stops_input = data.get('stops')
    if not isinstance(stops_input, list):
        stop_key = str(data.get('stop_location') or '').strip()
        stops_input = [stop_key] if stop_key else []
    if len(stops_input) > 2:
        return JsonResponse({'detail': 'Maximum 2 stops allowed'}, status=400)

    stops = []
    for raw_key in stops_input:
        key = str(raw_key or '').strip()
        if not key:
            continue
        resolved = _resolve_location_key(key)
        if not resolved:
            return JsonResponse({'detail': f'Invalid stop location: {key}'}, status=400)
        stops.append(resolved)

    distance_km = _compute_distance_km(
        (float(pickup_lat), float(pickup_lng)),
        (float(dropoff_lat), float(dropoff_lng)),
        [(stop[1], stop[2]) for stop in stops],
    )
    if distance_km <= 0:
        return JsonResponse({'detail': 'distance_km must be greater than 0'}, status=400)

    active_ride_exists = Ride.objects.filter(
        passenger=request.user,
        status__in=[
            Ride.RideStatus.SCHEDULED,
            Ride.RideStatus.REQUESTED,
            Ride.RideStatus.ACCEPTED,
            Ride.RideStatus.STARTED,
        ],
    ).exists()
    if active_ride_exists:
        return JsonResponse({'detail': 'You already have an active ride'}, status=400)

    candidates = _eligible_drivers(float(pickup_lat), float(pickup_lng), vehicle_type)
    if not candidates:
        return JsonResponse({'detail': 'No nearby drivers available'}, status=404)

    breakdown = _calculate_fare_breakdown(
        passenger=request.user,
        vehicle_type=vehicle_type,
        distance_km=distance_km,
        promo_code=promo_code,
    )
    fare_tzs = breakdown['final_fare']
    ride = Ride.objects.create(
        passenger=request.user,
        driver=None,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        distance_km=distance_km,
        fare_tzs=fare_tzs,
        status=Ride.RideStatus.REQUESTED,
        requested_vehicle_type=vehicle_type,
        promo_code=breakdown['promo_code'],
        promo_discount_pct=breakdown['promo_discount_pct'],
        surge_multiplier=breakdown['surge_multiplier'],
    )
    _apply_promo_usage(breakdown['promo_code'])
    for idx, stop in enumerate(stops, start=1):
        RideStop.objects.create(
            ride=ride,
            name=stop[0],
            latitude=Decimal(str(stop[1])),
            longitude=Decimal(str(stop[2])),
            stop_order=idx,
        )
    for driver in candidates:
        create_app_notification(
            user=driver.user,
            event='ride_requested',
            title='New Ride Request',
            message=f'Passenger requested a {vehicle_label(vehicle_type)} ride. Open incoming rides to accept.',
            payload={'ride_id': ride.id, 'vehicle_type': vehicle_type},
        )

    response = {
        'detail': 'Ride requested successfully',
        'ride': {
            'id': ride.id,
            'driver_id': ride.driver_id,
            'vehicle_type': vehicle_type,
            'status': ride.status,
            'fare_tzs': str(ride.fare_tzs),
            'pickup_lat': str(ride.pickup_lat),
            'pickup_lng': str(ride.pickup_lng),
            'dropoff_lat': str(ride.dropoff_lat),
            'dropoff_lng': str(ride.dropoff_lng),
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'stop_location': stops[0][0] if stops else None,
            'stops': _ride_stops_payload(ride),
            'passenger': _passenger_details(ride.passenger, request),
            'driver': _driver_details(ride.driver, request),
            'fare_breakdown': {
                'base_fare': str(breakdown['base_fare']),
                'price_per_km': str(breakdown['price_per_km']),
                'raw_fare': str(breakdown['raw_fare']),
                'surge_multiplier': str(breakdown['surge_multiplier']),
                'surged_fare': str(breakdown['surged_fare']),
                'first_ride_discount_pct': str(breakdown['first_ride_discount_pct']),
                'promo_code': breakdown['promo_code'],
                'promo_discount_pct': str(breakdown['promo_discount_pct']),
                'discount_amount': str(breakdown['discount_amount']),
                'final_fare': str(breakdown['final_fare']),
            },
        },
    }
    _store_idempotent_response(request.user, 'request_ride', request_id, response)
    return JsonResponse(response, status=201)


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER)
def ride_history(request: HttpRequest) -> JsonResponse:
    rides = Ride.objects.filter(passenger=request.user)
    payload = [
        {
            'id': ride.id,
            'driver_id': ride.driver_id,
            'vehicle_type': ride.requested_vehicle_type or getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', None),
            'status': ride.status,
            'fare_tzs': str(ride.fare_tzs),
            'distance_km': str(ride.distance_km),
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'stops': _ride_stops_payload(ride),
            'promo_code': ride.promo_code,
            'promo_discount_pct': str(ride.promo_discount_pct),
            'surge_multiplier': str(ride.surge_multiplier),
            'driver': _driver_details(ride.driver, request),
            'created_at': ride.created_at.isoformat(),
            'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
        }
        for ride in rides
    ]
    return JsonResponse({'rides': payload})


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER)
def current_ride(request: HttpRequest) -> JsonResponse:
    ride = (
        Ride.objects.filter(
            passenger=request.user,
            status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED],
        )
        .order_by('-created_at')
        .first()
    )

    if not ride:
        return JsonResponse({'ride': None})

    breakdown = _receipt_breakdown(ride)
    return JsonResponse(
        {
            'ride': {
                'id': ride.id,
                'driver_id': ride.driver_id,
                'vehicle_type': ride.requested_vehicle_type or getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', None),
                'status': ride.status,
                'fare_tzs': str(ride.fare_tzs),
                'distance_km': str(ride.distance_km),
                'pickup_lat': str(ride.pickup_lat),
                'pickup_lng': str(ride.pickup_lng),
                'dropoff_lat': str(ride.dropoff_lat),
                'dropoff_lng': str(ride.dropoff_lng),
                'pickup_location': ride.pickup_location_name(),
                'dropoff_location': ride.dropoff_location_name(),
                'stops': _ride_stops_payload(ride),
                'promo_code': ride.promo_code,
                'promo_discount_pct': str(ride.promo_discount_pct),
                'surge_multiplier': str(ride.surge_multiplier),
                'fare_breakdown': {k: str(v) for k, v in breakdown.items()},
                'driver': _driver_details(ride.driver, request),
                'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
            }
        }
    )


def _ride_for_user(request: HttpRequest, ride_id: int | None) -> Ride | None:
    if ride_id:
        return Ride.objects.filter(
            id=ride_id,
            passenger=request.user,
        ).first() or Ride.objects.filter(id=ride_id, driver=request.user).first()
    return _active_ride_for_user(request.user)


def _receipt_breakdown(ride: Ride) -> dict:
    base_fare = _read_setting_decimal(
        'base_fare_motorcycle_tzs'
        if ride.requested_vehicle_type == DriverProfile.VehicleType.MOTORCYCLE
        else 'base_fare_bajaji_tzs'
    )
    price_per_km = _read_setting_decimal('price_per_km_tzs')
    raw_fare = base_fare + (ride.distance_km * price_per_km)
    surge_multiplier = ride.surge_multiplier or Decimal('1.00')
    surged_fare = raw_fare * surge_multiplier
    discount_amount = max(Decimal('0'), surged_fare - ride.fare_tzs)
    return {
        'base_fare': base_fare,
        'price_per_km': price_per_km,
        'raw_fare': raw_fare,
        'surge_multiplier': surge_multiplier,
        'surged_fare': surged_fare,
        'promo_code': ride.promo_code,
        'promo_discount_pct': ride.promo_discount_pct,
        'discount_amount': discount_amount,
        'final_fare': ride.fare_tzs,
    }


@require_POST
@rate_limit(key_prefix='promo_validate', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def promo_validate(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    code = str(data.get('code') or '').strip()
    if not code:
        return JsonResponse({'detail': 'Promo code required'}, status=400)
    promo = PromoCode.objects.filter(code__iexact=code, is_active=True).first()
    if not promo:
        return JsonResponse({'detail': 'Promo code not found'}, status=404)
    if promo.expires_at and promo.expires_at <= timezone.now():
        return JsonResponse({'detail': 'Promo code expired'}, status=400)
    if promo.used_count >= promo.max_uses:
        return JsonResponse({'detail': 'Promo code limit reached'}, status=400)
    return JsonResponse({'code': promo.code, 'discount_pct': str(promo.discount_pct)})


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def ride_receipt(request: HttpRequest) -> JsonResponse:
    try:
        ride_id = int(request.GET.get('ride_id', ''))
    except ValueError:
        ride_id = None
    ride = _ride_for_user(request, ride_id)
    if not ride:
        return JsonResponse({'detail': 'Ride not found'}, status=404)
    breakdown = _receipt_breakdown(ride)
    return JsonResponse(
        {
            'ride': {
                'id': ride.id,
                'status': ride.status,
                'vehicle_type': ride.requested_vehicle_type,
                'pickup_location': ride.pickup_location_name(),
                'dropoff_location': ride.dropoff_location_name(),
                'stops': _ride_stops_payload(ride),
                'distance_km': str(ride.distance_km),
                'created_at': ride.created_at.isoformat(),
            },
            'breakdown': {k: str(v) for k, v in breakdown.items()},
        }
    )


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def ride_receipt_view(request: HttpRequest, ride_id: int) -> HttpResponse:
    ride = _ride_for_user(request, ride_id)
    if not ride:
        return HttpResponse('Ride not found', status=404)
    breakdown = _receipt_breakdown(ride)
    return render(
        request,
        'receipt.html',
        {
            'ride': ride,
            'breakdown': breakdown,
            'stops': _ride_stops_payload(ride),
        },
    )


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def ride_chat_messages(request: HttpRequest) -> JsonResponse:
    try:
        ride_id = int(request.GET.get('ride_id', ''))
    except ValueError:
        ride_id = None
    ride = _ride_for_user(request, ride_id)
    if not ride:
        return JsonResponse({'detail': 'Ride not found'}, status=404)
    if request.user not in {ride.passenger, ride.driver}:
        return JsonResponse({'detail': 'Forbidden'}, status=403)
    messages = ChatMessage.objects.filter(ride=ride).order_by('-created_at')[:50]
    payload = [
        {
            'id': msg.id,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender.first_name or msg.sender.username,
            'message': msg.message,
            'created_at': msg.created_at.isoformat(),
        }
        for msg in reversed(messages)
    ]
    return JsonResponse({'ride_id': ride.id, 'self_id': request.user.id, 'messages': payload})


@require_POST
@rate_limit(key_prefix='ride_chat_send', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def ride_chat_send(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    try:
        ride_id = int(data.get('ride_id', ''))
    except ValueError:
        ride_id = None
    ride = _ride_for_user(request, ride_id)
    if not ride:
        return JsonResponse({'detail': 'Ride not found'}, status=404)
    if request.user not in {ride.passenger, ride.driver}:
        return JsonResponse({'detail': 'Forbidden'}, status=403)
    message = str(data.get('message') or '').strip()
    if not message or len(message) > 500:
        return JsonResponse({'detail': 'Message must be 1-500 characters'}, status=400)
    chat = ChatMessage.objects.create(ride=ride, sender=request.user, message=message)
    other_user = ride.driver if request.user == ride.passenger else ride.passenger
    if other_user:
        create_app_notification(
            user=other_user,
            event='chat_message',
            title='New Message',
            message=message[:120],
            payload={'ride_id': ride.id, 'sender_id': request.user.id},
        )
    return JsonResponse(
        {
            'id': chat.id,
            'sender_id': chat.sender_id,
            'message': chat.message,
            'created_at': chat.created_at.isoformat(),
        },
        status=201,
    )


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def pending_ratings(request: HttpRequest) -> JsonResponse:
    role = _role(request.user)
    if role == UserProfile.Role.PASSENGER:
        rides = list(
            Ride.objects.select_related('driver')
            .filter(passenger=request.user, status=Ride.RideStatus.COMPLETED)
            .order_by('-created_at')[:5]
        )
        rated_ids = set(
            RideRating.objects.filter(ride__in=rides, rater=request.user).values_list('ride_id', flat=True)
        )
        payload = []
        for ride in rides:
            if ride.id in rated_ids or not ride.driver:
                continue
            payload.append(
                {
                    'ride_id': ride.id,
                    'target_id': ride.driver_id,
                    'target_name': ride.driver.first_name or ride.driver.username,
                    'target_role': 'driver',
                    'vehicle_type': ride.requested_vehicle_type,
                    'completed_at': ride.created_at.isoformat(),
                }
            )
        return JsonResponse({'pending': payload})

    rides = list(
        Ride.objects.select_related('passenger')
        .filter(driver=request.user, status=Ride.RideStatus.COMPLETED)
        .order_by('-created_at')[:5]
    )
    rated_ids = set(
        RideRating.objects.filter(ride__in=rides, rater=request.user).values_list('ride_id', flat=True)
    )
    payload = []
    for ride in rides:
        if ride.id in rated_ids:
            continue
        payload.append(
            {
                'ride_id': ride.id,
                'target_id': ride.passenger_id,
                'target_name': ride.passenger.first_name or ride.passenger.username,
                'target_role': 'passenger',
                'vehicle_type': ride.requested_vehicle_type,
                'completed_at': ride.created_at.isoformat(),
            }
        )
    return JsonResponse({'pending': payload})


@require_POST
@rate_limit(key_prefix='ride_rating', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def submit_rating(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    rating = data.get('rating')
    comment = str(data.get('comment') or '').strip()
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)
    try:
        rating_value = int(rating)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'rating must be 1-5'}, status=400)
    if rating_value < 1 or rating_value > 5:
        return JsonResponse({'detail': 'rating must be 1-5'}, status=400)

    try:
        ride = Ride.objects.get(id=ride_id, status=Ride.RideStatus.COMPLETED)
    except Ride.DoesNotExist:
        return JsonResponse({'detail': 'Completed ride not found'}, status=404)

    role = _role(request.user)
    if role == UserProfile.Role.PASSENGER:
        if ride.passenger_id != request.user.id or not ride.driver_id:
            return JsonResponse({'detail': 'Not allowed to rate this ride'}, status=403)
        target = ride.driver
        rater_role = RideRating.RaterRole.PASSENGER
    else:
        if ride.driver_id != request.user.id:
            return JsonResponse({'detail': 'Not allowed to rate this ride'}, status=403)
        target = ride.passenger
        rater_role = RideRating.RaterRole.DRIVER

    exists = RideRating.objects.filter(ride=ride, rater=request.user).exists()
    if exists:
        return JsonResponse({'detail': 'You have already rated this ride'}, status=400)

    rating_obj = RideRating.objects.create(
        ride=ride,
        rater=request.user,
        target=target,
        rater_role=rater_role,
        rating=rating_value,
        comment=comment[:500],
    )
    create_app_notification(
        user=target,
        event='new_rating',
        title='New Rating Received',
        message=f'You received a {rating_value}-star rating.',
        payload={'ride_id': ride.id, 'rating_id': rating_obj.id},
    )
    return JsonResponse({'detail': 'Rating submitted', 'rating_id': rating_obj.id}, status=201)


@require_GET
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_current_ride(request: HttpRequest) -> JsonResponse:
    ride = (
        Ride.objects.filter(
            driver=request.user,
            status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED],
        )
        .order_by('-created_at')
        .first()
    )
    if not ride:
        return JsonResponse({'ride': None})
    breakdown = _receipt_breakdown(ride)
    return JsonResponse(
        {
            'ride': {
                'id': ride.id,
                'status': ride.status,
                'vehicle_type': ride.requested_vehicle_type or getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', None),
                'pickup_lat': str(ride.pickup_lat),
                'pickup_lng': str(ride.pickup_lng),
                'dropoff_lat': str(ride.dropoff_lat),
                'dropoff_lng': str(ride.dropoff_lng),
                'pickup_location': ride.pickup_location_name(),
                'dropoff_location': ride.dropoff_location_name(),
                'stops': _ride_stops_payload(ride),
                'promo_code': ride.promo_code,
                'promo_discount_pct': str(ride.promo_discount_pct),
                'surge_multiplier': str(ride.surge_multiplier),
                'fare_breakdown': {k: str(v) for k, v in breakdown.items()},
                'passenger': _passenger_details(ride.passenger, request),
                'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
            }
        }
    )


@require_POST
@rate_limit(key_prefix='driver_profile', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def upsert_driver_profile(request: HttpRequest) -> JsonResponse:
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = request.POST
    else:
        data = _json_body(request)
    full_name = (data.get('full_name') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    email = (data.get('email') or '').strip()
    vehicle_type = data.get('vehicle_type')
    license_number = (data.get('license_number') or '').strip()
    plate_number = (data.get('plate_number') or '').strip()
    language = (data.get('language') or '').strip().lower()
    profile_image = request.FILES.get('profile_image')

    existing_profile = DriverProfile.objects.filter(user=request.user).first()
    if existing_profile:
        vehicle_type = vehicle_type or existing_profile.vehicle_type
        license_number = license_number or existing_profile.license_number
        plate_number = plate_number or existing_profile.plate_number

    if vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
        return JsonResponse({'detail': 'Invalid vehicle type'}, status=400)

    if not license_number:
        return JsonResponse({'detail': 'license_number is required'}, status=400)
    if not plate_number:
        return JsonResponse({'detail': 'plate_number is required'}, status=400)
    if profile_image:
        try:
            _validate_image_upload(profile_image)
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
    if full_name:
        request.user.first_name = full_name
    if phone_number:
        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
        exists = UserProfile.objects.exclude(user_id=request.user.id).filter(phone_number=phone_number).exists()
        if exists:
            return JsonResponse({'detail': 'Phone number already exists'}, status=400)
        profile = getattr(request.user, 'profile', None)
        if profile:
            profile.phone_number = phone_number
            profile.save(update_fields=['phone_number'])
        request.user.username = phone_number
    if email:
        if len(email) > 254 or '@' not in email:
            return JsonResponse({'detail': 'Invalid email address'}, status=400)
        email_exists = User.objects.exclude(id=request.user.id).filter(email=email).exists()
        if email_exists:
            return JsonResponse({'detail': 'Email is already registered'}, status=400)
        request.user.email = email
    request.user.save()

    profile, created = DriverProfile.objects.get_or_create(
        user=request.user,
        defaults={'vehicle_type': vehicle_type, 'license_number': license_number, 'plate_number': plate_number},
    )
    if not created:
        profile.vehicle_type = vehicle_type
        profile.license_number = license_number
        profile.plate_number = plate_number
    if profile_image:
        profile.profile_image = profile_image
    profile.save()
    if language:
        if language not in LANGUAGE_CHOICES:
            return JsonResponse({'detail': 'Invalid language'}, status=400)
        user_profile = getattr(request.user, 'profile', None)
        if user_profile:
            user_profile.language = language
            user_profile.save(update_fields=['language'])

    return JsonResponse(
        {
            'detail': 'Driver profile saved',
            'is_verified': profile.is_verified,
            'driver': _driver_details(request.user, request),
        }
    )


@require_GET
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_profile_me(request: HttpRequest) -> JsonResponse:
    return JsonResponse({'driver': _driver_details(request.user, request)})


@require_GET
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_documents_list(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'driver_profile', None)
    if not profile:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)
    payload = [
        {
            'doc_type': doc.doc_type,
            'status': doc.status,
            'scan_status': doc.scan_status,
            'scan_message': doc.scan_message,
            'scanned_at': doc.scanned_at.isoformat() if doc.scanned_at else None,
            'notes': doc.notes,
            'uploaded_at': doc.uploaded_at.isoformat(),
            'file_url': _absolute_media_url(request, doc.file),
        }
        for doc in profile.documents.all()
    ]
    return JsonResponse({'documents': payload})


@require_POST
@rate_limit(key_prefix='driver_documents_upload', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_documents_upload(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'driver_profile', None)
    if not profile:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)
    doc_type = (request.POST.get('doc_type') or '').strip()
    if doc_type not in DriverDocument.DocType.values:
        return JsonResponse({'detail': 'Invalid document type'}, status=400)
    file_obj = request.FILES.get('file')
    if not file_obj:
        return JsonResponse({'detail': 'Document file is required'}, status=400)
    allowed_doc_types = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
    content_type = (getattr(file_obj, 'content_type', '') or '').lower()
    if content_type and content_type not in allowed_doc_types:
        return JsonResponse({'detail': 'Unsupported document type. Use PDF, JPEG, PNG, or WEBP.'}, status=400)
    if file_obj.size > settings.MAX_PROFILE_IMAGE_BYTES * 4:
        return JsonResponse({'detail': 'File too large. Max 8MB.'}, status=400)
    try:
        _clamav_scan(file_obj)
    except ValidationError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)

    doc, _ = DriverDocument.objects.update_or_create(
        driver_profile=profile,
        doc_type=doc_type,
        defaults={
            'file': file_obj,
            'status': DriverDocument.Status.PENDING,
            'scan_status': DriverDocument.ScanStatus.PENDING,
            'scan_message': '',
            'scanned_at': None,
            'notes': '',
        },
    )
    create_app_notification(
        user=request.user,
        event='driver_doc_uploaded',
        title='Document Submitted',
        message=f'{doc.get_doc_type_display()} uploaded. Awaiting admin review.',
        payload={'doc_type': doc.doc_type},
    )
    return JsonResponse({'detail': 'Document uploaded', 'doc_type': doc.doc_type, 'status': doc.status})


@require_POST
@rate_limit(key_prefix='driver_online', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_online(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'driver_profile', None)
    if not profile:
        return JsonResponse({'detail': 'Create your driver profile first'}, status=400)
    if not profile.is_verified:
        return JsonResponse({'detail': 'Driver is not verified by admin yet'}, status=403)
    outstanding = _driver_outstanding_balance(profile)
    debt_limit = _driver_debt_limit()
    if outstanding >= debt_limit:
        return JsonResponse(
            {
                'detail': f'Driver settlement required before going online. Outstanding balance is TZS {outstanding}.',
                'outstanding_balance_tzs': str(outstanding),
                'debt_limit_tzs': str(debt_limit),
            },
            status=403,
        )

    data = _json_body(request)
    try:
        lat = Decimal(str(data.get('lat')))
        lng = Decimal(str(data.get('lng')))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'Invalid lat/lng'}, status=400)
    if not _valid_coordinate_pair(float(lat), float(lng)):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)

    profile.is_online = True
    profile.latitude = lat
    profile.longitude = lng
    profile.save(update_fields=['is_online', 'latitude', 'longitude'])

    return JsonResponse({'detail': 'Driver is online'})


@require_POST
@rate_limit(key_prefix='driver_offline', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_offline(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'driver_profile', None)
    if not profile:
        return JsonResponse({'detail': 'Driver profile not found'}, status=400)
    profile.is_online = False
    profile.save(update_fields=['is_online'])
    return JsonResponse({'detail': 'Driver is offline'})


@require_GET
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_incoming_rides(request: HttpRequest) -> JsonResponse:
    profile = getattr(request.user, 'driver_profile', None)
    base_qs = Ride.objects.filter(status=Ride.RideStatus.REQUESTED)

    assigned = list(base_qs.filter(driver=request.user))
    broadcast = []

    if profile and profile.is_online and profile.is_verified and profile.latitude is not None and profile.longitude is not None:
        radius_km = _read_setting_float('service_radius_km')
        unassigned = base_qs.filter(driver__isnull=True, requested_vehicle_type=profile.vehicle_type)
        for ride in unassigned:
            if cache.get(f'declined:{request.user.id}:{ride.id}'):
                continue
            distance = haversine_km(float(ride.pickup_lat), float(ride.pickup_lng), float(profile.latitude), float(profile.longitude))
            if distance <= radius_km:
                broadcast.append(ride)

    rides = assigned + broadcast
    payload = [
        {
            'id': ride.id,
            'status': ride.status,
            'pickup_lat': str(ride.pickup_lat),
            'pickup_lng': str(ride.pickup_lng),
            'dropoff_lat': str(ride.dropoff_lat),
            'dropoff_lng': str(ride.dropoff_lng),
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'fare_tzs': str(ride.fare_tzs),
            'distance_km': str(ride.distance_km),
            'stops': _ride_stops_payload(ride),
            'vehicle_type': ride.requested_vehicle_type,
            'passenger': _passenger_details(ride.passenger, request),
        }
        for ride in rides
    ]
    return JsonResponse({'rides': payload})


def _driver_ride_transition(request: HttpRequest, from_status: str, to_status: str):
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return None, JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    try:
        ride = Ride.objects.get(id=ride_id, driver=request.user, status=from_status)
    except Ride.DoesNotExist:
        return None, JsonResponse({'detail': 'Ride not found'}, status=404)

    ride.status = to_status
    ride.save(update_fields=['status'])
    return ride, None


@require_POST
@rate_limit(key_prefix='driver_accept', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_accept_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    driver_profile = getattr(request.user, 'driver_profile', None)
    if not driver_profile:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)
    if not driver_profile.is_verified:
        return JsonResponse({'detail': 'Driver is not verified by admin yet'}, status=403)
    if not driver_profile.is_online:
        return JsonResponse({'detail': 'Driver must be online to accept rides'}, status=403)

    with transaction.atomic():
        ride = Ride.objects.select_for_update().filter(id=ride_id, status=Ride.RideStatus.REQUESTED).first()
        if not ride:
            return JsonResponse({'detail': 'Ride not found or already accepted'}, status=404)
        if ride.driver_id and ride.driver_id != request.user.id:
            return JsonResponse({'detail': 'Ride already accepted by another driver'}, status=409)
        ride.driver = request.user
        ride.status = Ride.RideStatus.ACCEPTED
        ride.save(update_fields=['driver', 'status'])

    vehicle_type = getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', DriverProfile.VehicleType.MOTORCYCLE)
    create_app_notification(
        user=ride.passenger,
        event='ride_accepted',
        title='Ride Accepted',
        message=f'Your {vehicle_label(vehicle_type)} ride has been accepted by the driver.',
        payload={'ride_id': ride.id, 'status': ride.status, 'vehicle_type': vehicle_type},
    )

    # Notify other eligible drivers that the ride was taken.
    for other in _eligible_drivers(float(ride.pickup_lat), float(ride.pickup_lng), ride.requested_vehicle_type):
        if other.user_id == request.user.id:
            continue
        create_app_notification(
            user=other.user,
            event='ride_taken',
            title='Ride Taken',
            message='Ride already accepted by another driver.',
            payload={'ride_id': ride.id},
        )
    return JsonResponse({'detail': 'Ride accepted'})


@require_POST
@rate_limit(key_prefix='driver_start', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_start_ride(request: HttpRequest) -> JsonResponse:
    ride, error_response = _driver_ride_transition(request, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED)
    if error_response:
        return error_response
    vehicle_type = getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', DriverProfile.VehicleType.MOTORCYCLE)
    create_app_notification(
        user=ride.passenger,
        event='ride_started',
        title='Ride Started',
        message=f'Your {vehicle_label(vehicle_type)} ride has started.',
        payload={'ride_id': ride.id, 'status': ride.status, 'vehicle_type': vehicle_type},
    )
    return JsonResponse({'detail': 'Ride started'})


@require_POST
@rate_limit(key_prefix='driver_complete', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_complete_ride(request: HttpRequest) -> JsonResponse:
    ride, error_response = _driver_ride_transition(request, Ride.RideStatus.STARTED, Ride.RideStatus.COMPLETED)
    if error_response:
        return error_response
    driver_profile = getattr(request.user, 'driver_profile', None)
    commission = Decimal('0')
    if driver_profile:
        commission = _driver_commission_for_fare(ride.fare_tzs)
        DriverLedgerEntry.objects.create(
            driver_profile=driver_profile,
            ride=ride,
            entry_type=DriverLedgerEntry.EntryType.COMMISSION,
            amount_tzs=commission,
            note=f'Commission charged for ride #{ride.id}',
            created_by=request.user,
        )
    vehicle_type = getattr(getattr(ride.driver, 'driver_profile', None), 'vehicle_type', DriverProfile.VehicleType.MOTORCYCLE)
    create_app_notification(
        user=ride.passenger,
        event='ride_completed',
        title='Ride Completed',
        message=f'Your {vehicle_label(vehicle_type)} ride has been completed. Thank you.',
        payload={'ride_id': ride.id, 'status': ride.status, 'vehicle_type': vehicle_type},
    )
    create_app_notification(
        user=ride.passenger,
        event='rating_prompt',
        title='Rate Your Driver',
        message='Your ride is complete. Please rate your driver.',
        payload={'ride_id': ride.id},
    )
    create_app_notification(
        user=ride.driver,
        event='rating_prompt',
        title='Rate Your Passenger',
        message='Ride completed. Please rate your passenger.',
        payload={'ride_id': ride.id},
    )
    outstanding = _driver_outstanding_balance(driver_profile) if driver_profile else Decimal('0')
    return JsonResponse(
        {
            'detail': 'Ride completed',
            'commission_fee_tzs': str(commission),
            'outstanding_balance_tzs': str(outstanding),
        }
    )


@require_POST
@rate_limit(key_prefix='passenger_cancel', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.PASSENGER)
def passenger_cancel_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    ride = Ride.objects.filter(id=ride_id, passenger=request.user).first()
    if not ride:
        return JsonResponse({'detail': 'Ride not found'}, status=404)
    if ride.status not in {Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED}:
        return JsonResponse({'detail': 'Ride cannot be cancelled at this stage'}, status=400)

    ride.status = Ride.RideStatus.CANCELLED
    ride.save(update_fields=['status'])

    if ride.driver:
        create_app_notification(
            user=ride.driver,
            event='ride_cancelled',
            title='Ride Cancelled',
            message='The passenger cancelled this ride. You can accept another request now.',
            payload={'ride_id': ride.id, 'status': ride.status, 'vehicle_type': ride.requested_vehicle_type},
        )

    return JsonResponse({'detail': 'Ride cancelled'})


@require_POST
@rate_limit(key_prefix='driver_cancel', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_cancel_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    ride = Ride.objects.filter(id=ride_id, driver=request.user).first()
    if not ride:
        return JsonResponse({'detail': 'Ride not found'}, status=404)
    if ride.status not in {Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED}:
        return JsonResponse({'detail': 'Ride cannot be cancelled at this stage'}, status=400)

    ride.status = Ride.RideStatus.CANCELLED
    ride.save(update_fields=['status'])

    create_app_notification(
        user=ride.passenger,
        event='ride_cancelled',
        title='Ride Cancelled',
        message='Your driver cancelled this ride. Please request another driver.',
        payload={'ride_id': ride.id, 'status': ride.status, 'vehicle_type': ride.requested_vehicle_type},
    )
    return JsonResponse({'detail': 'Ride cancelled'})


@require_POST
@rate_limit(key_prefix='driver_decline', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_decline_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    ride = Ride.objects.filter(id=ride_id, status=Ride.RideStatus.REQUESTED, driver__isnull=True).first()
    if not ride:
        return JsonResponse({'detail': 'Ride not available to decline'}, status=404)

    cache.set(f'declined:{request.user.id}:{ride.id}', True, timeout=600)
    return JsonResponse({'detail': 'Ride declined'})


@require_GET
@login_required
@role_required(UserProfile.Role.DRIVER)
def driver_earnings(request: HttpRequest) -> JsonResponse:
    driver_profile = getattr(request.user, 'driver_profile', None)
    completed = Ride.objects.filter(driver=request.user, status=Ride.RideStatus.COMPLETED)
    total = completed.aggregate(total=Sum('fare_tzs'))['total'] or Decimal('0')
    commission = _driver_commission_summary(driver_profile) if driver_profile else {
        'outstanding_balance_tzs': '0',
        'debt_limit_tzs': str(_driver_debt_limit()),
        'is_over_limit': False,
        'today_fees_tzs': '0',
        'total_commission_tzs': '0',
        'total_settled_tzs': '0',
        'entries': [],
    }
    return JsonResponse(
        {
            'completed_rides': completed.count(),
            'total_earnings_tzs': str(total),
            'settlement_instructions': _driver_settlement_instructions(driver_profile) if driver_profile else {},
            **commission,
        }
    )


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_drivers(request: HttpRequest) -> JsonResponse:
    drivers = (
        DriverProfile.objects.select_related('user')
        .prefetch_related('documents')
        .all()
        .order_by('is_verified', 'id')
    )
    payload = []
    for driver in drivers:
        doc_statuses = {doc.doc_type: doc.status for doc in driver.documents.all()}
        payload.append(
            {
                **_driver_payload(driver),
                'station_name': getattr(getattr(driver.user, 'profile', None), 'driver_station_name', ''),
                'station_verified': getattr(getattr(driver.user, 'profile', None), 'driver_station_verified', False),
                'risk_flag': _risk_flag_for_user(driver.user, UserProfile.Role.DRIVER),
                'documents': doc_statuses,
                **_driver_commission_summary(driver),
            }
        )
    return JsonResponse({'drivers': payload})


@require_POST
@rate_limit(key_prefix='admin_driver_settlement', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_driver_settlement(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    driver_id = data.get('driver_id')
    amount_raw = data.get('amount_tzs')
    note = str(data.get('note') or '').strip()
    if not isinstance(driver_id, int):
        return JsonResponse({'detail': 'driver_id must be integer'}, status=400)
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'Invalid settlement amount'}, status=400)
    if amount <= 0:
        return JsonResponse({'detail': 'Settlement amount must be greater than zero'}, status=400)
    try:
        driver_profile = DriverProfile.objects.select_related('user').get(user_id=driver_id)
    except DriverProfile.DoesNotExist:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)

    outstanding = _driver_outstanding_balance(driver_profile)
    if outstanding <= 0:
        return JsonResponse({'detail': 'Driver has no outstanding commission balance'}, status=400)
    if amount > outstanding:
        return JsonResponse({'detail': 'Settlement amount cannot exceed outstanding balance'}, status=400)

    DriverLedgerEntry.objects.create(
        driver_profile=driver_profile,
        entry_type=DriverLedgerEntry.EntryType.SETTLEMENT,
        amount_tzs=-amount,
        note=note or 'Weekly commission settlement',
        created_by=request.user,
    )
    summary = _driver_commission_summary(driver_profile)
    return JsonResponse({'detail': 'Driver settlement recorded successfully', 'summary': summary})


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_passengers(request: HttpRequest) -> JsonResponse:
    passengers = (
        UserProfile.objects.select_related('user')
        .filter(role=UserProfile.Role.PASSENGER)
        .order_by('id')
    )
    payload = []
    for profile in passengers:
        payload.append(
            {
                **_passenger_payload(profile),
                'risk_flag': _risk_flag_for_user(profile.user, UserProfile.Role.PASSENGER),
            }
        )
    return JsonResponse({'passengers': payload})


@require_POST
@rate_limit(key_prefix='admin_verify_driver', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_verify_driver(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    driver_id = data.get('driver_id')
    if not isinstance(driver_id, int):
        return JsonResponse({'detail': 'driver_id must be integer'}, status=400)

    try:
        profile = DriverProfile.objects.get(user_id=driver_id)
    except DriverProfile.DoesNotExist:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)

    if profile.documents.exclude(scan_status=DriverDocument.ScanStatus.CLEAN).exists():
        return JsonResponse({'detail': 'Driver documents must be clean before verification'}, status=400)

    profile.is_verified = True
    profile.save(update_fields=['is_verified'])
    profile_phone = getattr(getattr(profile.user, 'profile', None), 'phone_number', '')
    if profile_phone:
        send_sms_notification(
            user=profile.user,
            phone_number=profile_phone,
            event='driver_verified',
            message='Habari! Your Zanzibar Bodaboda driver account has been verified. You can now go online.',
        )
    return JsonResponse({'detail': 'Driver verified'})


@require_POST
@rate_limit(key_prefix='admin_driver_doc_review', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_driver_document_review(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    driver_id = data.get('driver_id')
    doc_type = data.get('doc_type')
    status_value = data.get('status')
    notes = (data.get('notes') or '').strip()[:255]
    if not isinstance(driver_id, int):
        return JsonResponse({'detail': 'driver_id must be integer'}, status=400)
    if doc_type not in DriverDocument.DocType.values:
        return JsonResponse({'detail': 'Invalid doc_type'}, status=400)
    if status_value not in DriverDocument.Status.values:
        return JsonResponse({'detail': 'Invalid status'}, status=400)

    try:
        profile = DriverProfile.objects.get(user_id=driver_id)
    except DriverProfile.DoesNotExist:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)

    doc = DriverDocument.objects.filter(driver_profile=profile, doc_type=doc_type).first()
    if not doc:
        return JsonResponse({'detail': 'Document not found'}, status=404)

    doc.status = status_value
    doc.notes = notes
    doc.reviewed_at = timezone.now()
    doc.reviewed_by = request.user
    doc.save(update_fields=['status', 'notes', 'reviewed_at', 'reviewed_by'])

    create_app_notification(
        user=profile.user,
        event='driver_doc_reviewed',
        title='Document Reviewed',
        message=f'{doc.get_doc_type_display()} is {doc.status}.',
        payload={'doc_type': doc.doc_type, 'status': doc.status},
    )
    return JsonResponse({'detail': 'Document status updated'})


@require_POST
@rate_limit(key_prefix='admin_create_driver', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_create_driver(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    name = (data.get('name') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    password = data.get('password') or ''
    vehicle_type = data.get('vehicle_type')
    license_number = (data.get('license_number') or '').strip()
    plate_number = (data.get('plate_number') or '').strip()
    is_verified = bool(data.get('is_verified', False))

    if not name or not phone_number or not license_number or not plate_number:
        return JsonResponse({'detail': 'name, phone_number, license_number and plate_number are required'}, status=400)
    if not _validate_password_strength(password):
        return JsonResponse({'detail': 'Password must be at least 8 characters and include letters and numbers'}, status=400)
    if not _validate_phone_number(phone_number):
        return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
    if vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
        return JsonResponse({'detail': 'Invalid vehicle type'}, status=400)
    if UserProfile.objects.filter(phone_number=phone_number).exists():
        return JsonResponse({'detail': 'Phone number already exists'}, status=400)
    if DriverProfile.objects.filter(license_number=license_number).exists():
        return JsonResponse({'detail': 'License number already exists'}, status=400)

    user = User.objects.create_user(username=phone_number, password=password, first_name=name)
    UserProfile.objects.create(user=user, phone_number=phone_number, role=UserProfile.Role.DRIVER)
    driver = DriverProfile.objects.create(
        user=user,
        vehicle_type=vehicle_type,
        license_number=license_number,
        plate_number=plate_number,
        is_verified=is_verified,
    )
    send_sms_notification(
        user=user,
        phone_number=phone_number,
        event='driver_registration',
        message='Karibu Zanzibar Bodaboda! Your driver account has been created by admin.',
    )
    if is_verified:
        send_sms_notification(
            user=user,
            phone_number=phone_number,
            event='driver_verified',
            message='Habari! Your Zanzibar Bodaboda driver account is verified and ready to operate.',
        )
    return JsonResponse({'detail': 'Driver added successfully', 'driver': _driver_payload(driver)}, status=201)


@require_POST
@rate_limit(key_prefix='admin_create_passenger', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_create_passenger(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    name = (data.get('name') or '').strip()
    phone_number = (data.get('phone_number') or '').strip()
    password = data.get('password') or ''
    is_active = bool(data.get('is_active', True))

    if not name or not phone_number:
        return JsonResponse({'detail': 'name and phone_number are required'}, status=400)
    if not _validate_phone_number(phone_number):
        return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
    if not _validate_password_strength(password):
        return JsonResponse({'detail': 'Password must be at least 8 characters and include letters and numbers'}, status=400)
    if UserProfile.objects.filter(phone_number=phone_number).exists():
        return JsonResponse({'detail': 'Phone number already exists'}, status=400)

    user = User.objects.create_user(username=phone_number, password=password, first_name=name, is_active=is_active)
    profile = UserProfile.objects.create(user=user, phone_number=phone_number, role=UserProfile.Role.PASSENGER)
    send_sms_notification(
        user=user,
        phone_number=phone_number,
        event='passenger_registration',
        message='Karibu Zanzibar Bodaboda! Your passenger account has been created by admin.',
    )
    return JsonResponse({'detail': 'Passenger added successfully', 'passenger': _passenger_payload(profile)}, status=201)


@require_POST
@rate_limit(key_prefix='admin_update_driver', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_update_driver(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    driver_id = data.get('driver_id')
    if not isinstance(driver_id, int):
        return JsonResponse({'detail': 'driver_id must be integer'}, status=400)

    try:
        driver = DriverProfile.objects.select_related('user', 'user__profile').get(user_id=driver_id)
    except DriverProfile.DoesNotExist:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)

    name = data.get('name')
    phone_number = data.get('phone_number')
    vehicle_type = data.get('vehicle_type')
    license_number = data.get('license_number')
    plate_number = data.get('plate_number')
    is_verified = data.get('is_verified')
    is_online = data.get('is_online')

    if name is not None:
        driver.user.first_name = str(name).strip()
    if phone_number is not None:
        phone_number = str(phone_number).strip()
        if not phone_number:
            return JsonResponse({'detail': 'phone_number cannot be empty'}, status=400)
        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
        exists = UserProfile.objects.exclude(user_id=driver.user_id).filter(phone_number=phone_number).exists()
        if exists:
            return JsonResponse({'detail': 'Phone number already exists'}, status=400)
        driver.user.username = phone_number
        driver.user.profile.phone_number = phone_number
        driver.user.profile.save(update_fields=['phone_number'])

    if vehicle_type is not None:
        if vehicle_type not in {DriverProfile.VehicleType.MOTORCYCLE, DriverProfile.VehicleType.BAJAJI}:
            return JsonResponse({'detail': 'Invalid vehicle type'}, status=400)
        driver.vehicle_type = vehicle_type
    if license_number is not None:
        license_number = str(license_number).strip()
        if not license_number:
            return JsonResponse({'detail': 'license_number cannot be empty'}, status=400)
        exists = DriverProfile.objects.exclude(user_id=driver.user_id).filter(license_number=license_number).exists()
        if exists:
            return JsonResponse({'detail': 'License number already exists'}, status=400)
        driver.license_number = license_number
    if plate_number is not None:
        plate_number = str(plate_number).strip()
        if not plate_number:
            return JsonResponse({'detail': 'plate_number cannot be empty'}, status=400)
        driver.plate_number = plate_number
    if is_verified is not None:
        driver.is_verified = bool(is_verified)
    if is_online is not None:
        driver.is_online = bool(is_online)

    password = data.get('password')
    if password:
        if not _validate_password_strength(password):
            return JsonResponse({'detail': 'Password must be at least 8 characters and include letters and numbers'}, status=400)
        driver.user.set_password(password)

    driver.user.save()
    driver.save()

    return JsonResponse({'detail': 'Driver updated successfully', 'driver': _driver_payload(driver)})


@require_POST
@rate_limit(key_prefix='admin_update_passenger', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_update_passenger(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    passenger_id = data.get('passenger_id')
    if not isinstance(passenger_id, int):
        return JsonResponse({'detail': 'passenger_id must be integer'}, status=400)

    try:
        profile = UserProfile.objects.select_related('user').get(user_id=passenger_id, role=UserProfile.Role.PASSENGER)
    except UserProfile.DoesNotExist:
        return JsonResponse({'detail': 'Passenger profile not found'}, status=404)

    name = data.get('name')
    phone_number = data.get('phone_number')
    is_active = data.get('is_active')
    password = data.get('password')

    if name is not None:
        profile.user.first_name = str(name).strip()

    if phone_number is not None:
        phone_number = str(phone_number).strip()
        if not phone_number:
            return JsonResponse({'detail': 'phone_number cannot be empty'}, status=400)
        if not _validate_phone_number(phone_number):
            return JsonResponse({'detail': 'Invalid phone number format'}, status=400)
        exists = UserProfile.objects.exclude(user_id=profile.user_id).filter(phone_number=phone_number).exists()
        if exists:
            return JsonResponse({'detail': 'Phone number already exists'}, status=400)
        profile.phone_number = phone_number
        profile.user.username = phone_number

    if is_active is not None:
        profile.user.is_active = bool(is_active)

    if password:
        if not _validate_password_strength(password):
            return JsonResponse({'detail': 'Password must be at least 8 characters and include letters and numbers'}, status=400)
        profile.user.set_password(password)

    profile.user.save()
    profile.save()
    return JsonResponse({'detail': 'Passenger updated successfully', 'passenger': _passenger_payload(profile)})


@require_POST
@rate_limit(key_prefix='admin_delete_driver', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_delete_driver(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    driver_id = data.get('driver_id')
    if not isinstance(driver_id, int):
        return JsonResponse({'detail': 'driver_id must be integer'}, status=400)

    try:
        driver = DriverProfile.objects.select_related('user').get(user_id=driver_id)
    except DriverProfile.DoesNotExist:
        return JsonResponse({'detail': 'Driver profile not found'}, status=404)

    active_rides = Ride.objects.filter(
        driver=driver.user,
        status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED],
    ).exists()
    if active_rides:
        return JsonResponse({'detail': 'Cannot delete driver with active rides'}, status=400)

    driver.user.delete()
    return JsonResponse({'detail': 'Driver deleted successfully'})


@require_POST
@rate_limit(key_prefix='admin_delete_passenger', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_delete_passenger(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    passenger_id = data.get('passenger_id')
    if not isinstance(passenger_id, int):
        return JsonResponse({'detail': 'passenger_id must be integer'}, status=400)

    try:
        profile = UserProfile.objects.select_related('user').get(user_id=passenger_id, role=UserProfile.Role.PASSENGER)
    except UserProfile.DoesNotExist:
        return JsonResponse({'detail': 'Passenger profile not found'}, status=404)

    active_rides = Ride.objects.filter(
        passenger=profile.user,
        status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED],
    ).exists()
    if active_rides:
        return JsonResponse({'detail': 'Cannot delete passenger with active rides'}, status=400)

    profile.user.delete()
    return JsonResponse({'detail': 'Passenger deleted successfully'})


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_reports(request: HttpRequest) -> JsonResponse:
    cache_key = 'admin_reports_summary'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    total_drivers = DriverProfile.objects.count()
    total_passengers = UserProfile.objects.filter(role=UserProfile.Role.PASSENGER).count()
    verified_drivers = DriverProfile.objects.filter(is_verified=True).count()
    online_drivers = DriverProfile.objects.filter(is_online=True).count()

    rides = Ride.objects.all()
    completed_rides = rides.filter(status=Ride.RideStatus.COMPLETED)
    total_revenue = completed_rides.aggregate(total=Sum('fare_tzs'))['total'] or Decimal('0')
    total_commission = (
        DriverLedgerEntry.objects.filter(entry_type=DriverLedgerEntry.EntryType.COMMISSION).aggregate(total=Sum('amount_tzs'))['total']
        or Decimal('0')
    )
    total_settled = (
        DriverLedgerEntry.objects.filter(entry_type=DriverLedgerEntry.EntryType.SETTLEMENT).aggregate(total=Sum('amount_tzs'))['total']
        or Decimal('0')
    )

    top_drivers = (
        completed_rides.values('driver_id', 'driver__first_name')
        .annotate(total_rides=Count('id'), revenue=Sum('fare_tzs'))
        .order_by('-total_rides')[:5]
    )

    payload = {
        'summary': {
            'total_drivers': total_drivers,
            'total_passengers': total_passengers,
            'verified_drivers': verified_drivers,
            'pending_drivers': total_drivers - verified_drivers,
            'online_drivers': online_drivers,
            'total_rides': rides.count(),
            'completed_rides': completed_rides.count(),
            'cancelled_rides': rides.filter(status=Ride.RideStatus.CANCELLED).count(),
            'scheduled_rides': rides.filter(status=Ride.RideStatus.SCHEDULED).count(),
            'active_rides': rides.filter(
                status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED]
            ).count(),
            'total_revenue_tzs': str(total_revenue),
            'platform_commission_tzs': str(total_commission),
            'platform_settled_tzs': str(abs(total_settled)),
            'platform_outstanding_tzs': str(total_commission + total_settled),
        },
        'top_drivers': [
            {
                'driver_id': row['driver_id'],
                'name': row['driver__first_name'] or f"Driver {row['driver_id']}",
                'total_rides': row['total_rides'],
                'revenue_tzs': str(row['revenue'] or Decimal('0')),
            }
            for row in top_drivers
            if row['driver_id'] is not None
        ],
    }
    cache.set(cache_key, payload, timeout=60)
    return JsonResponse(payload)


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_monitoring(request: HttpRequest) -> JsonResponse:
    try:
        limit = int(request.GET.get('limit', '200'))
    except ValueError:
        limit = 200
    limit = max(20, min(limit, 500))
    try:
        offset = int(request.GET.get('offset', '0'))
    except ValueError:
        offset = 0
    offset = max(0, offset)

    window_start = timezone.now() - timedelta(hours=24)
    recent_qs = VisitEvent.objects.filter(created_at__gte=window_start)
    summary = {
        'last_24h_total': recent_qs.count(),
        'last_24h_page_views': recent_qs.filter(event_type=VisitEvent.EventType.PAGE_VIEW).count(),
        'last_24h_actions': recent_qs.filter(event_type=VisitEvent.EventType.ACTION).count(),
        'last_24h_registers': recent_qs.filter(event_type=VisitEvent.EventType.REGISTER).count(),
        'last_24h_logins': recent_qs.filter(event_type=VisitEvent.EventType.LOGIN).count(),
    }
    health = _database_health_snapshot()
    backup = _backup_health_snapshot()

    events = (
        VisitEvent.objects.select_related('user', 'user__profile')
        .all()
        .order_by('-created_at')[offset : offset + limit]
    )
    payload = []
    for event in events:
        profile = getattr(event.user, 'profile', None) if event.user else None
        payload.append(
            {
                'id': event.id,
                'event_type': event.event_type,
                'path': event.path,
                'method': event.method,
                'status_code': event.status_code,
                'ip_address': event.ip_address or '',
                'device_type': event.device_type,
                'os_name': event.os_name,
                'browser_name': event.browser_name,
                'country_code': event.country_code,
                'country_name': event.country_name,
                'region_name': event.region_name,
                'city_name': event.city_name,
                'timezone': event.timezone,
                'asn': event.asn,
                'isp': event.isp,
                'referrer': event.referrer,
                'user_agent': event.user_agent,
                'session_key': event.session_key,
                'created_at': event.created_at.isoformat(),
                'user_id': event.user_id,
                'user_name': event.user.first_name if event.user else '',
                'user_role': profile.role if profile else '',
                'user_phone': profile.phone_number if profile else '',
                'metadata': event.metadata or {},
            }
        )

    return JsonResponse(
        {
            'summary': summary,
            'health': health,
            'backup': backup,
            'events': payload,
            'offset': offset,
            'limit': limit,
        }
    )


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_settings(request: HttpRequest) -> JsonResponse:
    current = {}
    for key, default in DEFAULT_SETTINGS.items():
        current[key] = _read_setting(key) or default
    return JsonResponse({'settings': current})


@require_POST
@rate_limit(key_prefix='admin_update_settings', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_update_settings(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    settings = data.get('settings')
    if not isinstance(settings, dict):
        return JsonResponse({'detail': 'settings object is required'}, status=400)
    merged = {key: str(settings.get(key, _read_setting(key))).strip() for key in DEFAULT_SETTINGS}

    for key in DEFAULT_SETTINGS:
        if key not in settings:
            continue
        value = str(settings[key]).strip()
        if not value:
            return JsonResponse({'detail': f'{key} cannot be empty'}, status=400)
        if key.endswith('_km') or key.endswith('_tzs') or key == 'weather_rain_mm_threshold':
            try:
                if Decimal(value) <= 0:
                    return JsonResponse({'detail': f'{key} must be greater than 0'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': f'{key} must be numeric'}, status=400)
        if key in {'driver_settlement_provider', 'driver_settlement_phone', 'driver_settlement_reference_prefix'}:
            if len(value) < 2:
                return JsonResponse({'detail': f'{key} is too short'}, status=400)
        if key == 'surge_multiplier':
            try:
                if Decimal(value) < 1:
                    return JsonResponse({'detail': 'surge_multiplier must be >= 1'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': 'surge_multiplier must be numeric'}, status=400)
        if key == 'weather_lookahead_hours':
            try:
                val = int(Decimal(value))
                if val < 1 or val > 12:
                    return JsonResponse({'detail': 'weather_lookahead_hours must be between 1 and 12'}, status=400)
            except (InvalidOperation, ValueError):
                return JsonResponse({'detail': 'weather_lookahead_hours must be numeric'}, status=400)
        if key == 'weather_rain_probability_pct':
            try:
                val = Decimal(value)
                if val < 1 or val > 100:
                    return JsonResponse({'detail': 'weather_rain_probability_pct must be between 1 and 100'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': 'weather_rain_probability_pct must be numeric'}, status=400)
        if key == 'first_ride_discount_pct':
            try:
                val = Decimal(value)
                if val < 0 or val > 80:
                    return JsonResponse({'detail': 'first_ride_discount_pct must be between 0 and 80'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': 'first_ride_discount_pct must be numeric'}, status=400)
        if key == 'commission_band_medium_max_tzs':
            try:
                if Decimal(value) <= Decimal(merged['commission_band_short_max_tzs']):
                    return JsonResponse({'detail': 'commission_band_medium_max_tzs must be greater than short max'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': 'commission_band_medium_max_tzs must be numeric'}, status=400)
        if key == 'commission_band_long_max_tzs':
            try:
                medium = Decimal(merged['commission_band_medium_max_tzs'])
                if Decimal(value) <= medium:
                    return JsonResponse({'detail': 'commission_band_long_max_tzs must be greater than medium max'}, status=400)
            except InvalidOperation:
                return JsonResponse({'detail': 'commission_band_long_max_tzs must be numeric'}, status=400)
        SystemSetting.objects.update_or_create(key=key, defaults={'value': value})

    return JsonResponse({'detail': 'Settings updated successfully'})


def _weather_forecast_payload(lat: float, lng: float) -> dict:
    cache_key = f'weather_advisory:{round(lat, 3)}:{round(lng, 3)}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    lookahead_hours = max(1, min(_read_setting_int('weather_lookahead_hours'), 12))
    params = parse.urlencode(
        {
            'latitude': lat,
            'longitude': lng,
            'timezone': 'auto',
            'forecast_days': 1,
            'current': 'temperature_2m,weather_code,rain,showers,precipitation',
            'hourly': 'precipitation_probability,precipitation,weather_code,temperature_2m',
        }
    )
    url = f'https://api.open-meteo.com/v1/forecast?{params}'
    req = urlrequest.Request(url, headers={'User-Agent': 'BodaAU/1.0'})
    with urlrequest.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode('utf-8'))

    current = payload.get('current') or {}
    hourly = payload.get('hourly') or {}
    times = hourly.get('time') or []
    probabilities = hourly.get('precipitation_probability') or []
    precipitation = hourly.get('precipitation') or []
    codes = hourly.get('weather_code') or []

    now_value = current.get('time')
    max_probability = 0
    max_precipitation = Decimal('0')
    upcoming_codes = []
    if now_value and times:
        for idx, entry_time in enumerate(times):
            if entry_time < now_value:
                continue
            if len(upcoming_codes) >= lookahead_hours:
                break
            upcoming_codes.append(codes[idx] if idx < len(codes) else None)
            max_probability = max(max_probability, int(probabilities[idx] or 0))
            try:
                max_precipitation = max(max_precipitation, Decimal(str(precipitation[idx] or 0)))
            except InvalidOperation:
                continue

    probability_threshold = _read_setting_int('weather_rain_probability_pct')
    precipitation_threshold = _read_setting_decimal('weather_rain_mm_threshold')
    current_precipitation = Decimal(str(current.get('precipitation') or 0))
    current_code = current.get('weather_code')
    rain_expected = (
        max_probability >= probability_threshold
        or max_precipitation >= precipitation_threshold
        or current_precipitation >= precipitation_threshold
        or current_code in {51, 53, 55, 61, 63, 65, 80, 81, 82, 95}
        or any(code in {51, 53, 55, 61, 63, 65, 80, 81, 82, 95} for code in upcoming_codes if code is not None)
    )

    result = {
        'temperature_c': current.get('temperature_2m'),
        'weather_label': _weather_label(current_code),
        'current_precipitation_mm': str(current_precipitation),
        'rain_probability_pct': max_probability,
        'lookahead_hours': lookahead_hours,
        'rain_expected': rain_expected,
        'recommended_vehicle': 'bajaji' if rain_expected else 'motorcycle',
        'advice': (
            f'Rain is likely within the next {lookahead_hours} hours. It is better to take a bajaji.'
            if rain_expected
            else 'Weather looks stable right now. Bodaboda is fine if you prefer it.'
        ),
        'provider': 'Open-Meteo',
    }
    cache.set(cache_key, result, timeout=600)
    return result


@require_GET
@login_required
@role_required(UserProfile.Role.PASSENGER)
def passenger_weather_advisory(request: HttpRequest) -> JsonResponse:
    if not _setting_enabled('weather_advisory_enabled'):
        return JsonResponse({'enabled': False, 'detail': 'Weather advisory is disabled'})
    try:
        lat = float(request.GET.get('lat', ''))
        lng = float(request.GET.get('lng', ''))
    except ValueError:
        return JsonResponse({'detail': 'lat and lng are required'}, status=400)
    if not _valid_coordinate_pair(lat, lng):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)
    try:
        advisory = _weather_forecast_payload(lat, lng)
    except Exception:  # noqa: BLE001
        return JsonResponse({'detail': 'Weather service is unavailable right now'}, status=503)
    return JsonResponse({'enabled': True, 'advisory': advisory})


@require_GET
def locations_list(request: HttpRequest) -> JsonResponse:
    locations = get_active_locations()
    payload = [
        {'name': name, 'lat': lat, 'lng': lng, 'key': name.lower().replace(' ', '_')}
        for name, (lat, lng) in locations.items()
    ]
    return JsonResponse({'locations': payload})


@require_POST
@rate_limit(key_prefix='station_request', limit=5, window_seconds=3600)
def station_request_create(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    requested_name = str(data.get('requested_name') or '').strip()
    contact_phone = str(data.get('contact_phone') or '').strip()
    contact_email = str(data.get('contact_email') or '').strip()
    if not requested_name or len(requested_name) < 3:
        return JsonResponse({'detail': 'Station name is required'}, status=400)
    existing = Location.objects.filter(name__iexact=requested_name).exists()
    if existing:
        return JsonResponse({'detail': 'Station already exists'}, status=400)
    StationRequest.objects.create(
        requested_name=requested_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        status=StationRequest.Status.PENDING,
    )
    return JsonResponse({'detail': 'Station request submitted. We will review it shortly.'}, status=201)


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_station_requests(request: HttpRequest) -> JsonResponse:
    requests = StationRequest.objects.all()[:200]
    payload = [
        {
            'id': req.id,
            'requested_name': req.requested_name,
            'contact_phone': req.contact_phone,
            'contact_email': req.contact_email,
            'status': req.status,
            'admin_notes': req.admin_notes,
            'created_at': req.created_at.isoformat(),
        }
        for req in requests
    ]
    return JsonResponse({'requests': payload})


@require_POST
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_station_request_approve(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    request_id = data.get('request_id')
    if not isinstance(request_id, int):
        return JsonResponse({'detail': 'request_id must be integer'}, status=400)
    try:
        req = StationRequest.objects.get(id=request_id, status=StationRequest.Status.PENDING)
    except StationRequest.DoesNotExist:
        return JsonResponse({'detail': 'Request not found'}, status=404)
    lat = data.get('lat')
    lng = data.get('lng')
    try:
        lat_val = float(lat)
        lng_val = float(lng)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'lat and lng required for approval'}, status=400)
    Location.objects.update_or_create(
        name=req.requested_name,
        defaults={'latitude': lat_val, 'longitude': lng_val, 'is_active': True},
    )
    req.status = StationRequest.Status.APPROVED
    req.reviewed_at = timezone.now()
    req.admin_notes = (data.get('admin_notes') or '')[:255]
    req.save(update_fields=['status', 'reviewed_at', 'admin_notes'])
    return JsonResponse({'detail': 'Station approved'})


@require_GET
@rate_limit(key_prefix='geo_search', limit=20, window_seconds=60)
@login_required
def geo_search(request: HttpRequest) -> JsonResponse:
    query = (request.GET.get('q') or '').strip()
    if len(query) < 3:
        return JsonResponse({'results': []})

    cache_key = f'geo_search:{query.lower()}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse({'results': cached})

    params = parse.urlencode(
        {
            'format': 'json',
            'q': query,
            'countrycodes': 'tz',
            'limit': 5,
            'viewbox': '39.10,-5.70,39.60,-6.50',
            'bounded': 1,
        }
    )
    url = f"{settings.NOMINATIM_BASE_URL}?{params}"
    req = urlrequest.Request(url, headers={'User-Agent': 'BodabodaApp/1.0 (contact: support@bodaboda.local)'})
    try:
        with urlrequest.urlopen(req, timeout=settings.NOMINATIM_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return JsonResponse({'results': []})

    results = []
    for item in data[:5]:
        try:
            results.append(
                {
                    'name': item.get('display_name', '')[:160],
                    'lat': float(item.get('lat')),
                    'lng': float(item.get('lon')),
                }
            )
        except Exception:
            continue
    cache.set(cache_key, results, timeout=3600)
    return JsonResponse({'results': results})


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_emergency_alerts(request: HttpRequest) -> JsonResponse:
    alerts = EmergencyAlert.objects.select_related('user', 'ride').all()[:100]
    payload = [
        {
            'id': alert.id,
            'ride_id': alert.ride_id,
            'user_id': alert.user_id,
            'name': alert.user.first_name or alert.user.username,
            'phone_number': getattr(getattr(alert.user, 'profile', None), 'phone_number', ''),
            'role': alert.role_snapshot,
            'latitude': float(alert.latitude),
            'longitude': float(alert.longitude),
            'notified_contacts': alert.notified_contacts,
            'created_at': alert.created_at.isoformat(),
        }
        for alert in alerts
    ]
    return JsonResponse({'alerts': payload})


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_promos(request: HttpRequest) -> JsonResponse:
    promos = PromoCode.objects.all().order_by('-created_at')[:200]
    payload = [
        {
            'code': promo.code,
            'discount_pct': str(promo.discount_pct),
            'used_count': promo.used_count,
            'max_uses': promo.max_uses,
            'is_active': promo.is_active,
            'expires_at': promo.expires_at.isoformat() if promo.expires_at else None,
        }
        for promo in promos
    ]
    return JsonResponse({'promos': payload})


@require_POST
@rate_limit(key_prefix='admin_create_promo', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_create_promo(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    code = (data.get('code') or '').strip().upper()
    try:
        discount_pct = Decimal(str(data.get('discount_pct')))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'discount_pct must be numeric'}, status=400)
    max_uses = data.get('max_uses')
    try:
        max_uses = int(max_uses)
    except (TypeError, ValueError):
        max_uses = 100
    expires_at = data.get('expires_at')
    expires_value = None
    if expires_at:
        try:
            expires_value = datetime.fromisoformat(expires_at)
            if timezone.is_naive(expires_value):
                expires_value = timezone.make_aware(expires_value, timezone.get_current_timezone())
        except ValueError:
            return JsonResponse({'detail': 'expires_at must be ISO date'}, status=400)

    if not code or len(code) < 4:
        return JsonResponse({'detail': 'code must be at least 4 chars'}, status=400)
    if discount_pct <= 0 or discount_pct > 80:
        return JsonResponse({'detail': 'discount_pct must be between 1 and 80'}, status=400)
    if max_uses <= 0:
        return JsonResponse({'detail': 'max_uses must be > 0'}, status=400)

    promo, created = PromoCode.objects.get_or_create(
        code=code,
        defaults={
            'discount_pct': discount_pct,
            'max_uses': max_uses,
            'expires_at': expires_value,
            'is_active': True,
        },
    )
    if not created:
        return JsonResponse({'detail': 'Promo code already exists'}, status=400)
    return JsonResponse({'detail': 'Promo code created', 'code': promo.code})


@require_POST
@rate_limit(key_prefix='admin_toggle_promo', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_toggle_promo(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    code = (data.get('code') or '').strip().upper()
    is_active = bool(data.get('is_active', False))
    updated = PromoCode.objects.filter(code=code).update(is_active=is_active)
    if not updated:
        return JsonResponse({'detail': 'Promo code not found'}, status=404)
    return JsonResponse({'detail': 'Promo updated'})


@require_GET
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_scheduled_rides(request: HttpRequest) -> JsonResponse:
    rides = Ride.objects.filter(status=Ride.RideStatus.SCHEDULED).order_by('scheduled_for')[:100]
    payload = [
        {
            'id': ride.id,
            'passenger_name': ride.passenger.first_name or ride.passenger.username,
            'passenger_phone': getattr(getattr(ride.passenger, 'profile', None), 'phone_number', ''),
            'pickup_location': ride.pickup_location_name(),
            'dropoff_location': ride.dropoff_location_name(),
            'vehicle_type': ride.requested_vehicle_type,
            'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
            'status': ride.status,
            'stops': _ride_stops_payload(ride),
        }
        for ride in rides
    ]
    return JsonResponse({'rides': payload})


@require_POST
@rate_limit(key_prefix='admin_scheduled_cancel', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_cancel_scheduled_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    ride = (
        Ride.objects.select_related('passenger')
        .filter(id=ride_id, status=Ride.RideStatus.SCHEDULED)
        .first()
    )
    if not ride:
        return JsonResponse({'detail': 'Scheduled ride not found'}, status=404)

    ride.status = Ride.RideStatus.CANCELLED
    ride.save(update_fields=['status'])
    create_app_notification(
        user=ride.passenger,
        event='scheduled_cancelled',
        title='Scheduled Ride Cancelled',
        message='An admin cancelled your scheduled ride. You can reschedule anytime.',
        payload={'ride_id': ride.id},
    )
    return JsonResponse({'detail': 'Scheduled ride cancelled'})


@require_POST
@rate_limit(key_prefix='admin_scheduled_update', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
@role_required(UserProfile.Role.ADMIN)
def admin_update_scheduled_ride(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    ride_id = data.get('ride_id')
    if not isinstance(ride_id, int):
        return JsonResponse({'detail': 'ride_id must be integer'}, status=400)

    date_value = str(data.get('date', '')).strip()
    time_value = str(data.get('time', '')).strip()
    scheduled_for = _schedule_datetime_from_parts(date_value, time_value)
    if not scheduled_for:
        return JsonResponse({'detail': 'Valid date and time required'}, status=400)

    min_lead = timedelta(minutes=settings.SCHEDULED_MIN_LEAD_MINUTES)
    if scheduled_for <= timezone.now() + min_lead:
        return JsonResponse(
            {'detail': f'Scheduled time must be at least {settings.SCHEDULED_MIN_LEAD_MINUTES} minutes ahead'},
            status=400,
        )

    ride = (
        Ride.objects.select_related('passenger')
        .filter(id=ride_id, status=Ride.RideStatus.SCHEDULED)
        .first()
    )
    if not ride:
        return JsonResponse({'detail': 'Scheduled ride not found'}, status=404)

    ride.scheduled_for = scheduled_for
    ride.scheduled_search_started_at = None
    ride.save(update_fields=['scheduled_for', 'scheduled_search_started_at'])
    create_app_notification(
        user=ride.passenger,
        event='scheduled_rescheduled',
        title='Scheduled Ride Updated',
        message=f'Your scheduled ride was updated to {scheduled_for.strftime("%Y-%m-%d %H:%M")}.',
        payload={'ride_id': ride.id, 'scheduled_for': ride.scheduled_for.isoformat()},
    )
    return JsonResponse({'detail': 'Scheduled ride updated', 'scheduled_for': ride.scheduled_for.isoformat()})


@require_POST
@rate_limit(key_prefix='sos_trigger', limit=8, window_seconds=120)
@login_required
@role_required(UserProfile.Role.PASSENGER, UserProfile.Role.DRIVER)
def trigger_sos(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    if not bool(data.get('confirm')):
        return JsonResponse({'detail': 'SOS confirmation required'}, status=400)

    try:
        latitude = Decimal(str(data.get('lat')))
        longitude = Decimal(str(data.get('lng')))
    except (InvalidOperation, TypeError):
        return JsonResponse({'detail': 'Valid lat/lng required'}, status=400)

    if not _valid_coordinate_pair(float(latitude), float(longitude)):
        return JsonResponse({'detail': 'Invalid coordinate range'}, status=400)

    ride = _active_ride_for_user(request.user)
    if not ride:
        return JsonResponse({'detail': 'SOS is available only during an active ride'}, status=400)

    role = _role(request.user)
    contacts = list(EmergencyContact.objects.filter(user=request.user, is_active=True)[:5])
    message = (
        f'SOS ALERT: {request.user.first_name or request.user.username} triggered emergency alert. '
        f'Ride #{ride.id}, location: {latitude}, {longitude}.'
    )
    notified = 0
    for contact in contacts:
        send_sms_notification(
            user=request.user,
            phone_number=contact.phone_number,
            event='sos_alert',
            message=f'{message} Contact support/admin immediately.',
        )
        notified += 1

    alert = EmergencyAlert.objects.create(
        user=request.user,
        ride=ride,
        role_snapshot=EmergencyAlert.Role.DRIVER if role == UserProfile.Role.DRIVER else EmergencyAlert.Role.PASSENGER,
        latitude=latitude,
        longitude=longitude,
        notified_contacts=notified,
    )

    admin_users = User.objects.filter(is_active=True).filter(profile__role=UserProfile.Role.ADMIN) | User.objects.filter(
        is_active=True, is_superuser=True
    )
    for admin_user in admin_users.distinct():
        create_app_notification(
            user=admin_user,
            event='sos_alert',
            title='Emergency SOS',
            message=f'SOS from {request.user.first_name or request.user.username} on ride #{ride.id}.',
            payload={'alert_id': alert.id, 'ride_id': ride.id, 'lat': str(latitude), 'lng': str(longitude)},
        )

    return JsonResponse(
        {
            'detail': 'Emergency SOS sent',
            'alert_id': alert.id,
            'ride_id': ride.id,
            'notified_contacts': notified,
        },
        status=201,
    )


@require_GET
@login_required
def notifications_list(request: HttpRequest) -> JsonResponse:
    notifications = AppNotification.objects.filter(user=request.user).order_by('-created_at')[:20]
    payload = [
        {
            'id': n.id,
            'event': n.event,
            'title': n.title,
            'message': n.message,
            'payload': n.payload,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
        }
        for n in notifications
    ]
    unread_count = AppNotification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'unread_count': unread_count, 'notifications': payload})


@require_POST
@rate_limit(key_prefix='notifications_mark_read', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
def notifications_mark_read(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    notification_id = data.get('notification_id')
    mark_all = bool(data.get('mark_all', False))

    if mark_all:
        AppNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'detail': 'All notifications marked as read'})

    if not isinstance(notification_id, int):
        return JsonResponse({'detail': 'notification_id must be integer or use mark_all'}, status=400)

    updated = AppNotification.objects.filter(user=request.user, id=notification_id).update(is_read=True)
    if not updated:
        return JsonResponse({'detail': 'Notification not found'}, status=404)
    return JsonResponse({'detail': 'Notification marked as read'})


@require_POST
@rate_limit(key_prefix='notifications_clear', limit=settings.RATE_LIMIT_BURST_PER_MINUTE, window_seconds=60)
@login_required
def notifications_clear(request: HttpRequest) -> JsonResponse:
    AppNotification.objects.filter(user=request.user).delete()
    return JsonResponse({'detail': 'All notifications cleared'})


@require_GET
def app_version(request: HttpRequest) -> JsonResponse:
    response = JsonResponse(
        {
            'versionCode': getattr(settings, 'APP_VERSION_CODE', 1),
            'versionName': getattr(settings, 'APP_VERSION_NAME', '1.0'),
            'apkUrl': getattr(settings, 'APP_APK_URL', ''),
        }
    )
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    health = _database_health_snapshot()
    status = 200 if health['status'] == 'ok' else 503

    response = JsonResponse(
        {
            'status': health['status'],
            'database': health['database'],
            'error': health['error'],
            'monitoring': bool(getattr(settings, 'MONITORING_ENABLED', True)),
            'version': getattr(settings, 'APP_VERSION_NAME', '1.0'),
        },
        status=status,
    )
    response['Cache-Control'] = 'no-store'
    return response


def _push_token_payload(token: PushDeviceToken) -> dict:
    return {
        'device_token': token.device_token,
        'platform': token.platform,
        'device_id': token.device_id,
        'is_active': token.is_active,
        'last_seen_at': token.last_seen_at.isoformat(),
        'created_at': token.created_at.isoformat(),
    }


@require_GET
@login_required
def push_device_tokens_list(request: HttpRequest) -> JsonResponse:
    tokens = PushDeviceToken.objects.filter(user=request.user).order_by('-last_seen_at')
    return JsonResponse({'tokens': [_push_token_payload(token) for token in tokens], 'count': tokens.count()})


@require_POST
@rate_limit(key_prefix='push_token_upsert', limit=20, window_seconds=60)
@login_required
def push_device_tokens_register(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    device_token = str(data.get('device_token') or '').strip()
    if len(device_token) < 16:
        return JsonResponse({'detail': 'device_token is required'}, status=400)

    platform = str(data.get('platform') or PushDeviceToken.Platform.ANDROID).strip().lower()
    if platform not in PushDeviceToken.Platform.values:
        platform = PushDeviceToken.Platform.ANDROID
    device_id = str(data.get('device_id') or '').strip()[:128]
    is_active = bool(data.get('is_active', True))

    token, _ = PushDeviceToken.objects.update_or_create(
        device_token=device_token,
        defaults={
            'user': request.user,
            'platform': platform,
            'device_id': device_id,
            'is_active': is_active,
        },
    )
    return JsonResponse({'detail': 'Push token registered', 'token': _push_token_payload(token)}, status=201)


@require_POST
@rate_limit(key_prefix='push_token_remove', limit=20, window_seconds=60)
@login_required
def push_device_tokens_deactivate(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    device_token = str(data.get('device_token') or '').strip()
    if len(device_token) < 16:
        return JsonResponse({'detail': 'device_token is required'}, status=400)

    updated = PushDeviceToken.objects.filter(user=request.user, device_token=device_token).update(is_active=False)
    if not updated:
        return JsonResponse({'detail': 'Push token not found'}, status=404)
    return JsonResponse({'detail': 'Push token deactivated'})


@require_POST
@rate_limit(key_prefix='account_delete', limit=5, window_seconds=3600)
@login_required
def delete_account(request: HttpRequest) -> JsonResponse:
    data = _json_body(request)
    password = data.get('password') or ''
    if not password or not request.user.check_password(password):
        return JsonResponse({'detail': 'Password confirmation required'}, status=403)
    user = request.user
    logout(request)
    user.delete()
    return JsonResponse({'detail': 'Account deleted'})
