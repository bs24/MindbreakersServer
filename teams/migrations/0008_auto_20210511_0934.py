# Generated by Django 3.1.7 on 2021-05-11 07:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0007_team_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teamepisodelink',
            name='headstart',
            field=models.DurationField(default='00', help_text='The headstart value for this team'),
        ),
    ]
