from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0009_visitevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitevent',
            name='country_code',
            field=models.CharField(blank=True, default='', max_length=4),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='country_name',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='region_name',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='city_name',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='timezone',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='asn',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='visitevent',
            name='isp',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]
