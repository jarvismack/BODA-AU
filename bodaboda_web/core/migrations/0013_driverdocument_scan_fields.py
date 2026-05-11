from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0012_userprofile_email_verified'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverdocument',
            name='scan_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('clean', 'Clean'),
                    ('infected', 'Infected'),
                    ('error', 'Error'),
                ],
                default='pending',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='driverdocument',
            name='scan_message',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='driverdocument',
            name='scanned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
