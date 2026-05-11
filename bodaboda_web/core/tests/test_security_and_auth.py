import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase, override_settings

from django.utils import timezone

from core.models import DriverLedgerEntry, DriverProfile, EmergencyAlert, EmergencyContact, PushDeviceToken, Ride, RideRating, UserProfile
from core.security import get_client_ip


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class AuthAndSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def _create_passenger(self, phone='+255700000001', password='Pass12345'):
        user = User.objects.create_user(
            username=phone,
            password=password,
            first_name='Passenger One',
        )
        UserProfile.objects.create(user=user, phone_number=phone, role=UserProfile.Role.PASSENGER)
        return user

    def _create_driver(self, phone='+255700000099', password='Pass12345'):
        user = User.objects.create_user(
            username=phone,
            password=password,
            first_name='Driver One',
        )
        UserProfile.objects.create(user=user, phone_number=phone, role=UserProfile.Role.DRIVER)
        DriverProfile.objects.create(
            user=user,
            vehicle_type=DriverProfile.VehicleType.MOTORCYCLE,
            license_number='LIC-00099',
            plate_number='ZNZ-099',
            is_verified=True,
            is_online=True,
            latitude='-6.162800',
            longitude='39.204100',
        )
        return user

    def test_register_then_login_success(self):
        register_res = self.client.post(
            '/auth/register/',
            data={
                'full_name': 'Test Passenger',
                'phone_number': '+255700001111',
                'email': 'passenger@example.com',
                'password': 'Secure123',
                'role': UserProfile.Role.PASSENGER,
            },
            content_type='application/json',
        )
        self.assertEqual(register_res.status_code, 201)
        profile = UserProfile.objects.get(phone_number='+255700001111')
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])

        login_res = self.client.post(
            '/auth/login/',
            data={'phone_number': '+255700001111', 'password': 'Secure123'},
            content_type='application/json',
        )
        self.assertEqual(login_res.status_code, 200)

    def test_health_endpoint_reports_ok(self):
        res = self.client.get('/healthz/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('status'), 'ok')

    def test_push_device_token_registers(self):
        passenger = self._create_passenger(phone='+255700000126')
        self.client.force_login(passenger)

        res = self.client.post(
            '/api/push/tokens/register/',
            data={
                'device_token': 'token_abcdefghijklmnopqrstuvwxyz0123456789',
                'platform': 'android',
                'device_id': 'device-123',
            },
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(PushDeviceToken.objects.filter(user=passenger, is_active=True).count(), 1)

    def test_admin_monitoring_includes_health_and_backup(self):
        admin = User.objects.create_superuser(username='admin@example.com', email='admin@example.com', password='Pass12345')
        backup_dir = tempfile.TemporaryDirectory()
        backup_path = Path(backup_dir.name)
        (backup_path / 'db_20260415_140000.sqlite3').write_text('backup')
        try:
            with override_settings(BACKUP_DIR=backup_path):
                self.client.force_login(admin)
                res = self.client.get('/api/admin/monitoring/')
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn('health', data)
                self.assertIn('backup', data)
                self.assertEqual(data['backup']['count'], 1)
                self.assertEqual(data['backup']['latest_backup_name'], 'db_20260415_140000.sqlite3')
        finally:
            backup_dir.cleanup()

    def test_nearby_drivers_rejects_invalid_coordinate_range(self):
        passenger = self._create_passenger()
        self._create_driver()
        self.client.force_login(passenger)

        res = self.client.get('/api/passenger/nearby-drivers/?lat=190&lng=39.2&vehicle_type=motorcycle')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid coordinate range', res.json().get('detail', ''))

    def test_request_ride_rejects_invalid_coordinate_range(self):
        passenger = self._create_passenger(phone='+255700000002')
        self.client.force_login(passenger)

        res = self.client.post(
            '/api/passenger/request-ride/',
            data={
                'vehicle_type': DriverProfile.VehicleType.MOTORCYCLE,
                'pickup_lat': -6.16,
                'pickup_lng': 39.20,
                'dropoff_lat': -96.0,
                'dropoff_lng': 39.22,
                'distance_km': 2.5,
            },
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid coordinate range', res.json().get('detail', ''))

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_get_client_ip_does_not_trust_forwarded_header_by_default(self):
        request = self.factory.get('/', REMOTE_ADDR='10.0.0.10', HTTP_X_FORWARDED_FOR='8.8.8.8')
        self.assertEqual(get_client_ip(request), '10.0.0.10')

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_get_client_ip_trusts_forwarded_header_when_enabled(self):
        request = self.factory.get('/', REMOTE_ADDR='10.0.0.10', HTTP_X_FORWARDED_FOR='8.8.8.8, 1.1.1.1')
        self.assertEqual(get_client_ip(request), '8.8.8.8')

    def test_save_emergency_contacts(self):
        passenger = self._create_passenger(phone='+255700000123')
        self.client.force_login(passenger)

        res = self.client.post(
            '/api/emergency-contacts/upsert/',
            data={
                'contacts': [
                    {'name': 'Asha', 'phone_number': '+255711000001', 'relationship': 'Sister'},
                    {'name': 'Ali', 'phone_number': '+255711000002', 'relationship': 'Brother'},
                ]
            },
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(EmergencyContact.objects.filter(user=passenger).count(), 2)

    def test_trigger_sos_requires_active_ride(self):
        passenger = self._create_passenger(phone='+255700000124')
        self.client.force_login(passenger)

        res = self.client.post(
            '/api/sos/trigger/',
            data={'confirm': True, 'lat': -6.16, 'lng': 39.2},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('active ride', res.json().get('detail', '').lower())

    def test_trigger_sos_creates_alert_and_notifies_contacts(self):
        passenger = self._create_passenger(phone='+255700000125')
        driver_user = self._create_driver(phone='+255700000126')
        EmergencyContact.objects.create(
            user=passenger,
            name='Mama',
            phone_number='+255711100001',
            relationship='Mother',
            is_active=True,
        )
        Ride.objects.create(
            passenger=passenger,
            driver=driver_user,
            pickup_lat='-6.162800',
            pickup_lng='39.204100',
            dropoff_lat='-6.174500',
            dropoff_lng='39.217800',
            distance_km='2.10',
            fare_tzs='2970.00',
            status=Ride.RideStatus.ACCEPTED,
        )
        self.client.force_login(passenger)

        res = self.client.post(
            '/api/sos/trigger/',
            data={'confirm': True, 'lat': -6.1628, 'lng': 39.2041},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(EmergencyAlert.objects.count(), 1)
        self.assertEqual(EmergencyAlert.objects.first().notified_contacts, 1)

    def test_submit_rating_once_per_user(self):
        passenger = self._create_passenger(phone='+255700000201')
        driver_user = self._create_driver(phone='+255700000202')
        ride = Ride.objects.create(
            passenger=passenger,
            driver=driver_user,
            pickup_lat='-6.162800',
            pickup_lng='39.204100',
            dropoff_lat='-6.174500',
            dropoff_lng='39.217800',
            distance_km='2.10',
            fare_tzs='2970.00',
            status=Ride.RideStatus.COMPLETED,
            requested_vehicle_type=DriverProfile.VehicleType.MOTORCYCLE,
        )
        self.client.force_login(passenger)
        res = self.client.post(
            '/api/ride/rate/',
            data={'ride_id': ride.id, 'rating': 5, 'comment': 'Great ride'},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(RideRating.objects.filter(ride=ride, rater=passenger).count(), 1)

        res2 = self.client.post(
            '/api/ride/rate/',
            data={'ride_id': ride.id, 'rating': 4, 'comment': 'Second try'},
            content_type='application/json',
        )
        self.assertEqual(res2.status_code, 400)

    def test_schedule_ride_requires_future_time(self):
        passenger = self._create_passenger(phone='+255700000203')
        self.client.force_login(passenger)
        past = timezone.now() - timezone.timedelta(minutes=5)
        res = self.client.post(
            '/api/passenger/schedule-ride/',
            data={
                'vehicle_type': DriverProfile.VehicleType.MOTORCYCLE,
                'pickup_lat': -6.16,
                'pickup_lng': 39.20,
                'dropoff_lat': -6.17,
                'dropoff_lng': 39.22,
                'distance_km': 2.5,
                'date': past.date().isoformat(),
                'time': past.time().strftime('%H:%M'),
            },
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)

    def test_cancel_scheduled_ride(self):
        passenger = self._create_passenger(phone='+255700000204')
        ride = Ride.objects.create(
            passenger=passenger,
            pickup_lat='-6.162800',
            pickup_lng='39.204100',
            dropoff_lat='-6.174500',
            dropoff_lng='39.217800',
            distance_km='2.10',
            fare_tzs='2970.00',
            status=Ride.RideStatus.SCHEDULED,
            requested_vehicle_type=DriverProfile.VehicleType.MOTORCYCLE,
            scheduled_for=timezone.now() + timezone.timedelta(minutes=30),
        )
        self.client.force_login(passenger)
        res = self.client.post(
            '/api/passenger/scheduled-ride/cancel/',
            data={'ride_id': ride.id},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        ride.refresh_from_db()
        self.assertEqual(ride.status, Ride.RideStatus.CANCELLED)

    def test_driver_complete_ride_charges_commission(self):
        passenger = self._create_passenger(phone='+255700000301')
        driver_user = self._create_driver(phone='+255700000302')
        ride = Ride.objects.create(
            passenger=passenger,
            driver=driver_user,
            pickup_lat='-6.162800',
            pickup_lng='39.204100',
            dropoff_lat='-6.174500',
            dropoff_lng='39.217800',
            distance_km='2.10',
            fare_tzs='2000.00',
            status=Ride.RideStatus.STARTED,
            requested_vehicle_type=DriverProfile.VehicleType.MOTORCYCLE,
        )
        self.client.force_login(driver_user)

        res = self.client.post(
            '/api/driver/complete-ride/',
            data={'ride_id': ride.id},
            content_type='application/json',
        )

        self.assertEqual(res.status_code, 200)
        ride.refresh_from_db()
        self.assertEqual(ride.status, Ride.RideStatus.COMPLETED)
        ledger = DriverLedgerEntry.objects.get(ride=ride)
        self.assertEqual(ledger.entry_type, DriverLedgerEntry.EntryType.COMMISSION)
        self.assertEqual(str(ledger.amount_tzs), '100.00')

    def test_driver_online_blocked_when_outstanding_balance_reaches_limit(self):
        driver_user = self._create_driver(phone='+255700000303')
        driver_profile = driver_user.driver_profile
        DriverLedgerEntry.objects.create(
            driver_profile=driver_profile,
            entry_type=DriverLedgerEntry.EntryType.COMMISSION,
            amount_tzs='3000.00',
            note='Outstanding weekly balance',
        )
        self.client.force_login(driver_user)

        res = self.client.post(
            '/api/driver/online/',
            data={'lat': -6.1628, 'lng': 39.2041},
            content_type='application/json',
        )

        self.assertEqual(res.status_code, 403)
        self.assertIn('settlement required', res.json().get('detail', '').lower())

    def test_admin_can_record_driver_settlement(self):
        admin = User.objects.create_superuser(username='admin-settle', email='admin@boda.tz', password='Pass12345')
        driver_user = self._create_driver(phone='+255700000304')
        driver_profile = driver_user.driver_profile
        DriverLedgerEntry.objects.create(
            driver_profile=driver_profile,
            entry_type=DriverLedgerEntry.EntryType.COMMISSION,
            amount_tzs='400.00',
            note='Commission due',
        )
        self.client.force_login(admin)

        res = self.client.post(
            '/api/admin/driver/settlement/',
            data={'driver_id': driver_user.id, 'amount_tzs': 250, 'note': 'Week 1 payment'},
            content_type='application/json',
        )

        self.assertEqual(res.status_code, 200)
        settlement = DriverLedgerEntry.objects.filter(driver_profile=driver_profile, entry_type=DriverLedgerEntry.EntryType.SETTLEMENT).first()
        self.assertIsNotNone(settlement)
        self.assertEqual(str(settlement.amount_tzs), '-250.00')

    @patch('core.views.urlrequest.urlopen')
    def test_passenger_weather_advisory_recommends_bajaji_when_rain_likely(self, mock_urlopen):
        passenger = self._create_passenger(phone='+255700000305')
        self.client.force_login(passenger)
        fake_response = MagicMock()
        fake_response.read.return_value = b'''{
          "current": {
            "time": "2026-05-07T10:00",
            "temperature_2m": 27.4,
            "weather_code": 3,
            "precipitation": 0.0
          },
          "hourly": {
            "time": ["2026-05-07T10:00", "2026-05-07T11:00", "2026-05-07T12:00"],
            "precipitation_probability": [25, 78, 82],
            "precipitation": [0.0, 0.4, 1.2],
            "weather_code": [3, 61, 63],
            "temperature_2m": [27.4, 27.0, 26.7]
          }
        }'''
        mock_urlopen.return_value.__enter__.return_value = fake_response

        res = self.client.get('/api/passenger/weather-advisory/?lat=-6.1628&lng=39.2041')

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['advisory']['rain_expected'])
        self.assertEqual(data['advisory']['recommended_vehicle'], 'bajaji')
