from django.apps import AppConfig


class MdblistrrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mdblistrr'

    def ready(self):
        from . import cron  # Register scheduled tasks on app load.
