# Generated by Django 2.2.11 on 2020-10-21 02:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('huntserver', '0066_auto_20201020_2200'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='puzzle',
            name='resource_link',
        ),
        migrations.RemoveField(
            model_name='puzzle',
            name='solution_link',
        ),
    ]
