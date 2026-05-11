from decimal import Decimal
from math import radians, sin, cos, atan2, sqrt

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


ACTIVE_ZANZIBAR_LOCATIONS = {
    'Stone Town': (-6.1659, 39.2026),
    'Malindi': (-6.1643, 39.1894),
    'Forodhani': (-6.1629, 39.1936),
    'Darajani': (-6.1669, 39.2085),
    'Mlandege': (-6.1758, 39.2127),
    'Amaan Stadium': (-6.1585, 39.1897),
    'Chukwani': (-6.2238, 39.2152),
    'Kisauni Airport': (-6.2220, 39.2247),
    'Fumba': (-6.3189, 39.2502),
    'Bweleo': (-6.3134, 39.3246),
    'Dunga': (-6.2703, 39.2893),
    'Mwera': (-6.2504, 39.3053),
    'Mangapwani': (-6.0053, 39.1758),
    'Mkokotoni': (-5.8796, 39.2205),
    'Nungwi': (-5.7265, 39.2933),
    'Kendwa': (-5.7374, 39.2985),
    'Kiwengwa': (-5.9892, 39.3763),
    'Matemwe': (-5.8857, 39.3677),
    'Paje': (-6.2649, 39.5358),
    'Jambiani': (-6.3239, 39.5616),
    'Michamvi': (-6.1849, 39.5101),
    'Chwaka': (-6.1596, 39.4362),
    'Makunduchi': (-6.3466, 39.5535),
    'Kwanyanya': (-6.1628, 39.2041),
    'Mbuzini Hospital': (-6.1745, 39.2178),
    'Njia ya Kama': (-6.1492, 39.2135),
    'Bububu Skuli': (-6.1029, 39.2451),
    'Kidichi': (-6.0903, 39.2338),
    'Njia ya Bumbwini': (-6.0668, 39.2214),
}


class UserProfile(models.Model):
    class Role(models.TextChoices):
        PASSENGER = 'passenger', 'Passenger'
        DRIVER = 'driver', 'Driver'
        ADMIN = 'admin', 'Admin'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PASSENGER)
    profile_image = models.ImageField(upload_to='profiles/passengers/', null=True, blank=True)
    language = models.CharField(max_length=8, default='en')
    email_verified = models.BooleanField(default=False)
    driver_station_name = models.CharField(max_length=120, blank=True, default='')
    driver_station_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    driver_station_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    driver_station_verified = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f'{self.user.username} ({self.role})'


class DriverProfile(models.Model):
    class VehicleType(models.TextChoices):
        MOTORCYCLE = 'motorcycle', 'Motorcycle'
        BAJAJI = 'bajaji', 'Bajaji'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.MOTORCYCLE)
    license_number = models.CharField(max_length=64, unique=True)
    plate_number = models.CharField(max_length=32, blank=True, default='')
    profile_image = models.ImageField(upload_to='profiles/drivers/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.user.username} - {self.vehicle_type}'

    def current_location_name(self) -> str:
        if self.latitude is None or self.longitude is None:
            return 'Unknown'
        return closest_active_location(float(self.latitude), float(self.longitude))

    def outstanding_commission_balance(self) -> Decimal:
        total = self.ledger_entries.aggregate(total=models.Sum('amount_tzs'))['total']
        return total or Decimal('0')


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class StationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    requested_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=20, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_notes = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.requested_name} ({self.status})'


class Ride(models.Model):
    class RideStatus(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        REQUESTED = 'requested', 'Requested'
        ACCEPTED = 'accepted', 'Accepted'
        STARTED = 'started', 'Started'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    passenger = models.ForeignKey(User, on_delete=models.CASCADE, related_name='passenger_rides')
    driver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='driver_rides')
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6)
    distance_km = models.DecimalField(max_digits=7, decimal_places=2)
    fare_tzs = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=RideStatus.choices, default=RideStatus.REQUESTED)
    requested_vehicle_type = models.CharField(max_length=20, choices=DriverProfile.VehicleType.choices, default=DriverProfile.VehicleType.MOTORCYCLE)
    promo_code = models.CharField(max_length=32, blank=True, default='')
    promo_discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    surge_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.00'))
    scheduled_for = models.DateTimeField(null=True, blank=True)
    scheduled_search_started_at = models.DateTimeField(null=True, blank=True)
    scheduled_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def pickup_location_name(self) -> str:
        return closest_active_location(float(self.pickup_lat), float(self.pickup_lng))

    def dropoff_location_name(self) -> str:
        return closest_active_location(float(self.dropoff_lat), float(self.dropoff_lng))


class RideRating(models.Model):
    class RaterRole(models.TextChoices):
        PASSENGER = 'passenger', 'Passenger'
        DRIVER = 'driver', 'Driver'

    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='ratings')
    rater = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    target = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_received')
    rater_role = models.CharField(max_length=20, choices=RaterRole.choices)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['ride', 'rater'], name='unique_rating_per_ride_rater')
        ]

    def __str__(self) -> str:
        return f'ride:{self.ride_id}:rater:{self.rater_id}:rating:{self.rating}'


class RideStop(models.Model):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='stops')
    name = models.CharField(max_length=120)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    stop_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['stop_order']

    def __str__(self) -> str:
        return f'ride:{self.ride_id}:stop:{self.name}'


class ChatMessage(models.Model):
    ride = models.ForeignKey(Ride, on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'ride:{self.ride_id}:sender:{self.sender_id}'


class PromoCode(models.Model):
    code = models.CharField(max_length=32, unique=True)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(80)])
    max_uses = models.PositiveIntegerField(default=100)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.code} ({self.discount_pct}%)'


class DriverDocument(models.Model):
    class DocType(models.TextChoices):
        NATIONAL_ID = 'national_id', 'National ID'
        LICENSE = 'license', 'Driver License'
        VEHICLE_INSURANCE = 'vehicle_insurance', 'Vehicle Insurance'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class ScanStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CLEAN = 'clean', 'Clean'
        INFECTED = 'infected', 'Infected'
        ERROR = 'error', 'Error'

    driver_profile = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=32, choices=DocType.choices)
    file = models.FileField(upload_to='driver_docs/')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    scan_message = models.CharField(max_length=255, blank=True, default='')
    scanned_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_driver_docs')

    class Meta:
        ordering = ['-uploaded_at']
        constraints = [
            models.UniqueConstraint(fields=['driver_profile', 'doc_type'], name='unique_driver_doc_type')
        ]

    def __str__(self) -> str:
        return f'driver:{self.driver_profile_id}:{self.doc_type}:{self.status}'


class DriverLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        COMMISSION = 'commission', 'Commission Charge'
        SETTLEMENT = 'settlement', 'Settlement Payment'
        ADJUSTMENT = 'adjustment', 'Admin Adjustment'

    driver_profile = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name='ledger_entries')
    ride = models.ForeignKey(Ride, null=True, blank=True, on_delete=models.SET_NULL, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount_tzs = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='driver_ledger_actions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self) -> str:
        return f'driver:{self.driver_profile_id}:{self.entry_type}:{self.amount_tzs}'


class IdempotencyKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='idempotency_keys')
    key = models.CharField(max_length=64)
    endpoint = models.CharField(max_length=128)
    response_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'key', 'endpoint'], name='unique_idempotency_key')
        ]

    def __str__(self) -> str:
        return f'{self.user_id}:{self.endpoint}:{self.key}'


class SystemSetting(models.Model):
    key = models.CharField(max_length=64, unique=True)
    value = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f'{self.key}={self.value}'


class PushDeviceToken(models.Model):
    class Platform(models.TextChoices):
        ANDROID = 'android', 'Android'
        IOS = 'ios', 'iOS'
        WEB = 'web', 'Web'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_tokens')
    device_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=16, choices=Platform.choices, default=Platform.ANDROID)
    device_id = models.CharField(max_length=128, blank=True, default='')
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['platform', 'is_active']),
        ]

    def __str__(self) -> str:
        return f'{self.user_id}:{self.platform}:{self.device_token[:12]}'


class NotificationLog(models.Model):
    class Status(models.TextChoices):
        SIMULATED = 'simulated', 'Simulated'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='notification_logs')
    phone_number = models.CharField(max_length=20)
    event = models.CharField(max_length=64)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SIMULATED)
    provider_message_id = models.CharField(max_length=128, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.phone_number} {self.event} {self.status}'


class VisitEvent(models.Model):
    class EventType(models.TextChoices):
        PAGE_VIEW = 'page_view', 'Page View'
        ACTION = 'action', 'Action'
        REGISTER = 'register', 'Register'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='visit_events')
    session_key = models.CharField(max_length=64, blank=True, default='')
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    path = models.CharField(max_length=180, blank=True, default='')
    method = models.CharField(max_length=10, blank=True, default='')
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    device_type = models.CharField(max_length=32, blank=True, default='')
    os_name = models.CharField(max_length=64, blank=True, default='')
    browser_name = models.CharField(max_length=64, blank=True, default='')
    country_code = models.CharField(max_length=4, blank=True, default='')
    country_name = models.CharField(max_length=64, blank=True, default='')
    region_name = models.CharField(max_length=64, blank=True, default='')
    city_name = models.CharField(max_length=64, blank=True, default='')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default='')
    asn = models.CharField(max_length=32, blank=True, default='')
    isp = models.CharField(max_length=120, blank=True, default='')
    referrer = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self) -> str:
        return f'{self.event_type}:{self.path}:{self.created_at}'


class AppNotification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='app_notifications')
    event = models.CharField(max_length=64)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.user_id}:{self.event}:{self.title}'


class EmergencyContact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emergency_contacts')
    name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20)
    relationship = models.CharField(max_length=64, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.user_id}:{self.name}:{self.phone_number}'


class EmergencyAlert(models.Model):
    class Role(models.TextChoices):
        PASSENGER = 'passenger', 'Passenger'
        DRIVER = 'driver', 'Driver'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emergency_alerts')
    ride = models.ForeignKey(Ride, null=True, blank=True, on_delete=models.SET_NULL, related_name='emergency_alerts')
    role_snapshot = models.CharField(max_length=20, choices=Role.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    notified_contacts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'alert:{self.id}:ride:{self.ride_id}:user:{self.user_id}'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius * c


def get_active_locations() -> dict[str, tuple[float, float]]:
    try:
        rows = Location.objects.filter(is_active=True).values_list('name', 'latitude', 'longitude')
        merged = dict(ACTIVE_ZANZIBAR_LOCATIONS)
        for name, lat, lng in rows:
            merged[name] = (float(lat), float(lng))
        return merged
    except Exception:
        pass
    return ACTIVE_ZANZIBAR_LOCATIONS


def closest_active_location(lat: float, lng: float) -> str:
    closest_name = 'Unknown'
    closest_distance = None
    for name, (loc_lat, loc_lng) in get_active_locations().items():
        distance = haversine_km(lat, lng, loc_lat, loc_lng)
        if closest_distance is None or distance < closest_distance:
            closest_name = name
            closest_distance = distance
    return closest_name


def calculate_fare(vehicle_type: str, distance_km: Decimal) -> Decimal:
    base_fare = Decimal('1500') if vehicle_type == DriverProfile.VehicleType.MOTORCYCLE else Decimal('2500')
    price_per_km = Decimal('700')
    return base_fare + (distance_km * price_per_km)
