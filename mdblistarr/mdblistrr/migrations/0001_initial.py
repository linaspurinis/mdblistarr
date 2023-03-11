# Generated by Django 4.1.7 on 2023-03-11 17:26

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Log',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('date', models.DateTimeField()),
                ('status', models.IntegerField()),
                ('provider', models.IntegerField()),
                ('text', models.TextField()),
            ],
            options={
                'verbose_name_plural': 'log',
            },
        ),
        migrations.CreateModel(
            name='Preferences',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('value', models.CharField(max_length=255, null=True)),
            ],
            options={
                'verbose_name_plural': 'preferences',
            },
        ),
    ]
