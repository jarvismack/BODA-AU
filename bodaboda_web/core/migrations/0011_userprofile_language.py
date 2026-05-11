from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0010_visitevent_geo'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='language',
            field=models.CharField(default='en', max_length=8),
        ),
    ]
