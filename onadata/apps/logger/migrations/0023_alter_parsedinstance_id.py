# Generated by Django 3.2 on 2022-04-27 19:05

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('logger', '0022_misc_model_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
    ]
