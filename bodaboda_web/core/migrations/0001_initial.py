from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(max_length=20, unique=True)),
                ('role', models.CharField(choices=[('passenger', 'Passenger'), ('driver', 'Driver'), ('admin', 'Admin')], default='passenger', max_length=20)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='DriverProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_type', models.CharField(choices=[('motorcycle', 'Motorcycle'), ('bajaji', 'Bajaji')], default='motorcycle', max_length=20)),
                ('license_number', models.CharField(max_length=64, unique=True)),
                ('is_verified', models.BooleanField(default=False)),
                ('is_online', models.BooleanField(default=False)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='driver_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Ride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pickup_lat', models.DecimalField(decimal_places=6, max_digits=9)),
                ('pickup_lng', models.DecimalField(decimal_places=6, max_digits=9)),
                ('dropoff_lat', models.DecimalField(decimal_places=6, max_digits=9)),
                ('dropoff_lng', models.DecimalField(decimal_places=6, max_digits=9)),
                ('distance_km', models.DecimalField(decimal_places=2, max_digits=7)),
                ('fare_tzs', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('requested', 'Requested'), ('accepted', 'Accepted'), ('started', 'Started'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='requested', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('driver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='driver_rides', to=settings.AUTH_USER_MODEL)),
                ('passenger', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='passenger_rides', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
