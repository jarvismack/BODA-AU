from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_rename_core_visitevent_event_t_4f0521_idx_core_visite_event_t_75a026_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PushDeviceToken',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('device_token', models.CharField(max_length=255, unique=True)),
                (
                    'platform',
                    models.CharField(
                        choices=[('android', 'Android'), ('ios', 'iOS'), ('web', 'Web')],
                        default='android',
                        max_length=16,
                    ),
                ),
                ('device_id', models.CharField(blank=True, default='', max_length=128)),
                ('is_active', models.BooleanField(default=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='push_tokens',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-last_seen_at'],
                'indexes': [
                    models.Index(fields=['user', 'is_active'], name='core_push_user_act_0c7b53_idx'),
                    models.Index(fields=['platform', 'is_active'], name='core_push_platf_0f0a40_idx'),
                ],
            },
        ),
    ]
