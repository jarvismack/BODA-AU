from django.contrib import admin

from .models import (
    AppNotification,
    DriverLedgerEntry,
    DriverProfile,
    EmergencyAlert,
    EmergencyContact,
    PromoCode,
    ChatMessage,
    RideStop,
    DriverDocument,
    IdempotencyKey,
    NotificationLog,
    Ride,
    RideRating,
    SystemSetting,
    UserProfile,
    Location,
    StationRequest,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'phone_number', 'role')
    search_fields = ('user__username', 'phone_number')


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'vehicle_type', 'is_verified', 'is_online', 'current_location', 'coordinates')
    search_fields = ('user__username', 'license_number')
    readonly_fields = ('current_location',)

    @admin.display(description='Current Location')
    def current_location(self, obj: DriverProfile):
        return obj.current_location_name()

    @admin.display(description='Coordinates')
    def coordinates(self, obj: DriverProfile):
        if obj.latitude is None or obj.longitude is None:
            return '-'
        return f'{obj.latitude}, {obj.longitude}'


@admin.register(DriverLedgerEntry)
class DriverLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'driver_profile', 'entry_type', 'amount_tzs', 'ride', 'created_by', 'created_at')
    list_filter = ('entry_type',)
    search_fields = ('driver_profile__user__username', 'note', 'ride__id')


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'passenger',
        'driver',
        'pickup_location',
        'dropoff_location',
        'status',
        'requested_vehicle_type',
        'scheduled_for',
        'fare_tzs',
        'created_at',
    )
    list_filter = ('status',)
    readonly_fields = ('pickup_coordinates', 'dropoff_coordinates')

    @admin.display(description='Pickup')
    def pickup_location(self, obj: Ride):
        return obj.pickup_location_name()

    @admin.display(description='Dropoff')
    def dropoff_location(self, obj: Ride):
        return obj.dropoff_location_name()

    @admin.display(description='Pickup Coordinates')
    def pickup_coordinates(self, obj: Ride):
        return f'{obj.pickup_lat}, {obj.pickup_lng}'

    @admin.display(description='Dropoff Coordinates')
    def dropoff_coordinates(self, obj: Ride):
        return f'{obj.dropoff_lat}, {obj.dropoff_lng}'


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'updated_at')
    search_fields = ('key',)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'phone_number', 'event', 'status', 'provider_message_id', 'created_at')
    list_filter = ('status', 'event')
    search_fields = ('phone_number', 'provider_message_id', 'event')


@admin.register(AppNotification)
class AppNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'event', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'event')
    search_fields = ('user__username', 'title', 'message')


@admin.register(RideRating)
class RideRatingAdmin(admin.ModelAdmin):
    list_display = ('id', 'ride', 'rater', 'target', 'rater_role', 'rating', 'created_at')
    list_filter = ('rater_role', 'rating')
    search_fields = ('ride__id', 'rater__username', 'target__username')


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'phone_number', 'relationship', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'name', 'phone_number')


@admin.register(EmergencyAlert)
class EmergencyAlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'ride', 'role_snapshot', 'latitude', 'longitude', 'notified_contacts', 'created_at')
    list_filter = ('role_snapshot',)
    search_fields = ('user__username', 'ride__id')


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_pct', 'used_count', 'max_uses', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'ride', 'sender', 'message', 'created_at')
    search_fields = ('ride__id', 'sender__username', 'message')


@admin.register(RideStop)
class RideStopAdmin(admin.ModelAdmin):
    list_display = ('id', 'ride', 'name', 'stop_order')
    search_fields = ('ride__id', 'name')


@admin.register(DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'driver_profile', 'doc_type', 'status', 'scan_status', 'uploaded_at', 'reviewed_at')
    list_filter = ('status', 'scan_status', 'doc_type')
    search_fields = ('driver_profile__user__username',)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'endpoint', 'key', 'created_at')
    search_fields = ('user__username', 'endpoint', 'key')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'latitude', 'longitude', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(StationRequest)
class StationRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'requested_name', 'contact_phone', 'contact_email', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('requested_name', 'contact_phone', 'contact_email')
