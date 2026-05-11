from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_userprofile_language'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
    ]
