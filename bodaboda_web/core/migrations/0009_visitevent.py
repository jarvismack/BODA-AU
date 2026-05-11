from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0008_promocode_ride_promo_code_ride_promo_discount_pct_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisitEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(blank=True, default='', max_length=64)),
                ('event_type', models.CharField(choices=[('page_view', 'Page View'), ('action', 'Action'), ('register', 'Register'), ('login', 'Login'), ('logout', 'Logout')], max_length=20)),
                ('path', models.CharField(blank=True, default='', max_length=180)),
                ('method', models.CharField(blank=True, default='', max_length=10)),
                ('status_code', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, default='', max_length=255)),
                ('device_type', models.CharField(blank=True, default='', max_length=32)),
                ('os_name', models.CharField(blank=True, default='', max_length=64)),
                ('browser_name', models.CharField(blank=True, default='', max_length=64)),
                ('referrer', models.CharField(blank=True, default='', max_length=255)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='visit_events', to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='visitevent',
            index=models.Index(fields=['event_type', 'created_at'], name='core_visitevent_event_t_4f0521_idx'),
        ),
        migrations.AddIndex(
            model_name='visitevent',
            index=models.Index(fields=['user', 'created_at'], name='core_visitevent_user_id_2ec0e6_idx'),
        ),
    ]
