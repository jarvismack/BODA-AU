from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0013_driverdocument_scan_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='driver_station_name',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='driver_station_lat',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='driver_station_lng',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='driver_station_verified',
            field=models.BooleanField(default=False),
        ),
    ]
