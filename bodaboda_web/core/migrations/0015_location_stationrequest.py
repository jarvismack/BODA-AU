from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0014_userprofile_driver_station'),
    ]

    operations = [
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                ('latitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('longitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='StationRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_name', models.CharField(max_length=120)),
                ('contact_phone', models.CharField(blank=True, default='', max_length=20)),
                ('contact_email', models.EmailField(blank=True, default='', max_length=254)),
                (
                    'status',
                    models.CharField(
                        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                        default='pending',
                        max_length=16,
                    ),
                ),
                ('admin_notes', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
