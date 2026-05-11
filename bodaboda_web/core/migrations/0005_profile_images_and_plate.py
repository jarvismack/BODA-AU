from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_appnotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverprofile',
            name='plate_number',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='driverprofile',
            name='profile_image',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/drivers/'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='profile_image',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/passengers/'),
        ),
    ]
