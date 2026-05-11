from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from core.models import DriverProfile, Ride, SystemSetting
from core.services import create_app_notification, send_sms_notification
from core.views import vehicle_label
from core.models import haversine_km


class Command(BaseCommand):
    help = 'Assign drivers to scheduled rides shortly before pickup time.'

    def handle(self, *args, **options):
        now = timezone.now()
        lead_minutes = settings.SCHEDULED_MATCH_LEAD_MINUTES
        retry_minutes = settings.SCHEDULED_MATCH_RETRY_MINUTES

        due_cutoff = now + timedelta(minutes=lead_minutes)
        retry_cutoff = now - timedelta(minutes=retry_minutes)

        rides = Ride.objects.filter(
            status=Ride.RideStatus.SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=due_cutoff,
        ).filter(
            models.Q(scheduled_search_started_at__isnull=True)
            | models.Q(scheduled_search_started_at__lte=retry_cutoff)
        )

        processed = 0
        matched = 0
        for ride in rides:
            processed += 1
            if ride.scheduled_reminder_sent_at is None:
                create_app_notification(
                    user=ride.passenger,
                    event='scheduled_reminder',
                    title='Ride Reminder',
                    message=f'Your scheduled ride is in about {lead_minutes} minutes.',
                    payload={'ride_id': ride.id, 'lead_minutes': lead_minutes},
                )
                passenger_phone = getattr(getattr(ride.passenger, 'profile', None), 'phone_number', '')
                if passenger_phone:
                    send_sms_notification(
                        user=ride.passenger,
                        phone_number=passenger_phone,
                        event='scheduled_reminder',
                        message=f'Zanzibar Bodaboda: Your scheduled ride starts in {lead_minutes} minutes.',
                    )
                ride.scheduled_reminder_sent_at = now
            ride.scheduled_search_started_at = now
            vehicle_type = ride.requested_vehicle_type

            drivers = DriverProfile.objects.filter(
                is_online=True, is_verified=True, vehicle_type=vehicle_type
            ).exclude(latitude__isnull=True, longitude__isnull=True)

            radius_setting = SystemSetting.objects.filter(key='service_radius_km').first()
            try:
                radius_km = float(radius_setting.value) if radius_setting else 3.0
            except (TypeError, ValueError):
                radius_km = 3.0

            nearby = []
            for driver in drivers:
                distance = haversine_km(float(ride.pickup_lat), float(ride.pickup_lng), float(driver.latitude), float(driver.longitude))
                if distance <= radius_km:
                    busy = Ride.objects.filter(
                        driver=driver.user,
                        status__in=[Ride.RideStatus.REQUESTED, Ride.RideStatus.ACCEPTED, Ride.RideStatus.STARTED],
                    ).exists()
                    if not busy:
                        nearby.append((driver, distance))

            if not nearby:
                create_app_notification(
                    user=ride.passenger,
                    event='scheduled_no_driver',
                    title='No Driver Yet',
                    message='We could not find a driver yet for your scheduled ride. Retrying shortly.',
                    payload={'ride_id': ride.id},
                )
                ride.save(update_fields=['scheduled_search_started_at', 'scheduled_reminder_sent_at'])
                continue

            nearby.sort(key=lambda item: item[1])
            ride.driver = None
            ride.status = Ride.RideStatus.REQUESTED
            ride.save(update_fields=['driver', 'status', 'scheduled_search_started_at', 'scheduled_reminder_sent_at'])
            matched += 1

            for driver, _distance in nearby:
                create_app_notification(
                    user=driver.user,
                    event='ride_requested',
                    title='Scheduled Ride Request',
                    message=f'Passenger scheduled a {vehicle_label(vehicle_type)} ride. Please accept.',
                    payload={'ride_id': ride.id, 'vehicle_type': vehicle_type},
                )
                create_app_notification(
                    user=driver.user,
                    event='scheduled_pre_alert',
                    title='Upcoming Scheduled Ride',
                    message=f'Ride #{ride.id} is starting soon. Please be ready to accept.',
                    payload={
                        'ride_id': ride.id,
                        'scheduled_for': ride.scheduled_for.isoformat() if ride.scheduled_for else None,
                        'lead_minutes': lead_minutes,
                    },
                )
            create_app_notification(
                user=ride.passenger,
                event='scheduled_match_started',
                title='Searching for Driver',
                message='We are matching your scheduled ride with a driver now.',
                payload={'ride_id': ride.id},
            )

        self.stdout.write(self.style.SUCCESS(f'Processed {processed} scheduled rides, matched {matched}.'))
