# models.py
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save, pre_delete
from .crypto import decrypt, encrypt, SECRET_PREF_NAMES

class EncryptedCharField(models.CharField):
    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def to_python(self, value):
        return decrypt(value)

    def get_prep_value(self, value):
        return encrypt(value)

class Preferences(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    value = models.CharField(max_length=2048, null=True)

    @classmethod
    def secret_names(cls):
        return SECRET_PREF_NAMES

    @classmethod
    def get_value(cls, name, default=None):
        pref = cls.objects.filter(name=name).first()
        return pref.value if pref is not None else default

    @classmethod
    def set_value(cls, name, value):
        pref, _ = cls.objects.update_or_create(name=name, defaults={"value": value})
        return pref

    @classmethod
    def get_secret(cls, name, default=None):
        if name not in SECRET_PREF_NAMES:
            raise ValueError(f"{name} is not configured as a secret preference")
        pref = cls.objects.filter(name=name).first()
        if pref is None or pref.value in (None, ""):
            return default
        return decrypt(pref.value)

    @classmethod
    def set_secret(cls, name, value):
        if name not in SECRET_PREF_NAMES:
            raise ValueError(f"{name} is not configured as a secret preference")
        encrypted = encrypt(value)
        pref, _ = cls.objects.update_or_create(name=name, defaults={"value": encrypted})
        pref.value = encrypted
        return pref

    @classmethod
    def clear_secret(cls, name):
        return cls.set_secret(name, "")

    def save(self, *args, **kwargs):
        if self.name in SECRET_PREF_NAMES:
            self.value = encrypt(self.value)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "preferences"

    def __str__(self):
        return self.name

class RadarrInstance(models.Model):
    MINIMUM_AVAILABILITY_CHOICES = [
        ('announced', 'Announced'),
        ('inCinemas', 'In Cinemas'),
        ('released', 'Released'),
        ('preDB', 'PreDB'),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    apikey = EncryptedCharField(max_length=2048)
    quality_profile = models.CharField(max_length=255)
    root_folder = models.CharField(max_length=255)
    minimum_availability = models.CharField(
        max_length=20, choices=MINIMUM_AVAILABILITY_CHOICES, default='released'
    )
    tags = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class SonarrInstance(models.Model):
    MONITOR_CHOICES = [
        ('all', 'All Episodes'),
        ('future', 'Future Episodes'),
        ('missing', 'Missing Episodes'),
        ('existing', 'Existing Episodes'),
        ('recent', 'Recent Episodes'),
        ('pilot', 'Pilot Episode'),
        ('firstSeason', 'First Season'),
        ('latestSeason', 'Latest Season'),
        ('none', 'None'),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    apikey = EncryptedCharField(max_length=2048)
    quality_profile = models.CharField(max_length=255)
    root_folder = models.CharField(max_length=255)
    monitor = models.CharField(max_length=20, choices=MONITOR_CHOICES, default='all')
    tags = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PlexSyncRun(models.Model):
    """
    Tracks a single sync_plex_posters() execution (manual or cron-triggered)
    so the UI can show live progress via polling and request cancellation,
    instead of blocking the request that started it.
    """
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('complete', 'Complete'),
        ('cancelled', 'Cancelled'),
        ('error', 'Error'),
    ]
    KIND_CHOICES = [
        ('sync', 'Sync'),
        ('reset', 'Reset to original'),
    ]

    id = models.AutoField(primary_key=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='sync')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    total_items = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    stamped = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    current_title = models.CharField(max_length=255, blank=True, default='')
    cancel_requested = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default='')

    def __str__(self):
        return f"PlexSyncRun#{self.id} {self.status}"

class PlexInstance(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    token = EncryptedCharField(max_length=2048)
    server_client_identifier = models.CharField(max_length=255, blank=True, default='')
    library_ids = models.CharField(max_length=500, blank=True, default='')
    badge_score_enabled = models.BooleanField(default=True)
    badge_age_rating_enabled = models.BooleanField(default=True)
    sync_audience_rating_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PlexPosterState(models.Model):
    """
    Tracks what mdblistarr last stamped onto a Plex item's poster, so a sync
    run only re-composites/re-uploads when the underlying score/age rating or
    the poster art itself has actually changed (see last_thumb_key /
    last_uploaded_thumb_key below).
    """
    id = models.BigAutoField(primary_key=True)
    plex_instance = models.ForeignKey(PlexInstance, on_delete=models.CASCADE, related_name='poster_states')
    rating_key = models.CharField(max_length=50)
    section_id = models.CharField(max_length=50, blank=True, default='')
    section_type = models.CharField(max_length=10, blank=True, default='')
    imdb_id = models.CharField(max_length=20, blank=True, null=True)
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    tvdb_id = models.PositiveIntegerField(blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)

    stamped_score = models.IntegerField(blank=True, null=True)
    stamped_age_rating = models.CharField(max_length=20, blank=True, null=True)

    # Plex's `thumb` value carries a revision token that changes whenever the
    # poster art changes. last_thumb_key is the value we last observed;
    # last_uploaded_thumb_key is the value Plex assigned right after *our*
    # last upload, used to tell "still our poster" apart from "something
    # replaced it" without downloading/hashing the image every run.
    last_thumb_key = models.CharField(max_length=255, blank=True, default='')
    last_uploaded_thumb_key = models.CharField(max_length=255, blank=True, default='')
    original_poster_cache_path = models.CharField(max_length=500, blank=True, default='')

    # Audience-rating override (optional, off by default): original_audience_rating
    # is the RT/IMDb-sourced value Plex had before our first override — cached once,
    # so the value is recoverable if the feature is turned off. synced_audience_rating
    # is the value (Plex's 0-10 scale) we last set, for change detection.
    original_audience_rating = models.FloatField(blank=True, null=True)
    synced_audience_rating = models.FloatField(blank=True, null=True)

    mdblist_checked_at = models.DateTimeField(blank=True, null=True)
    stamped_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['plex_instance', 'rating_key'], name='uniq_plex_poster_state'),
        ]
        indexes = [
            models.Index(fields=['plex_instance', 'imdb_id'], name='idx_plex_poster_imdb'),
        ]

    def __str__(self):
        return f"{self.plex_instance_id}:{self.rating_key} {self.title or ''}".strip()

class InstanceChangeLog(models.Model):
    INSTANCE_TYPES = [
        ('radarr', 'Radarr'),
        ('sonarr', 'Sonarr'),
    ]
    EVENT_TYPES = [
        ('added', 'Added'),
        ('deleted', 'Deleted'),
        ('name_changed', 'Name Changed'),
    ]
    
    instance_type = models.CharField(max_length=10, choices=INSTANCE_TYPES)
    instance_id = models.IntegerField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    old_value = models.CharField(max_length=100, null=True, blank=True)
    new_value = models.CharField(max_length=100, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

@receiver(pre_save, sender=RadarrInstance)
def radarr_instance_about_to_save(sender, instance, **kwargs):
    if instance.pk:  # Only for existing instances, not new ones
        try:
            # Get the current state from DB before save happens
            instance._old_instance = RadarrInstance.objects.get(pk=instance.pk)
        except RadarrInstance.DoesNotExist:
            pass
        
# Signal handlers to track changes
@receiver(post_save, sender=RadarrInstance)
def radarr_instance_saved(sender, instance, created, **kwargs):
    print('radarr_instance_saved')
    if created:
        InstanceChangeLog.objects.create(
            instance_type='radarr',
            instance_id=instance.id,
            event_type='added',
            new_value=instance.name
        )
    else:
        # Check for name change using the cached old instance
        if hasattr(instance, '_old_instance') and instance._old_instance.name != instance.name:
            InstanceChangeLog.objects.create(
                instance_type='radarr',
                instance_id=instance.id,
                event_type='name_changed',
                old_value=instance._old_instance.name,
                new_value=instance.name
            )

@receiver(pre_delete, sender=RadarrInstance)
def radarr_instance_deleted(sender, instance, **kwargs):
    InstanceChangeLog.objects.create(
        instance_type='radarr',
        instance_id=instance.id,
        event_type='deleted',
        old_value=instance.name
    )

@receiver(pre_save, sender=SonarrInstance)
def rsonarr_instance_about_to_save(sender, instance, **kwargs):
    if instance.pk:  # Only for existing instances, not new ones
        try:
            # Get the current state from DB before save happens
            instance._old_instance = SonarrInstance.objects.get(pk=instance.pk)
        except SonarrInstance.DoesNotExist:
            pass

# Sonarr signal handlers
@receiver(post_save, sender=SonarrInstance)
def sonarr_instance_saved(sender, instance, created, **kwargs):
    if created:
        InstanceChangeLog.objects.create(
            instance_type='sonarr',
            instance_id=instance.id,
            event_type='added',
            new_value=instance.name
        )
    else:
        # Check for name change using the cached old instance
        if hasattr(instance, '_old_instance') and instance._old_instance.name != instance.name:
            InstanceChangeLog.objects.create(
                instance_type='sonarr',
                instance_id=instance.id,
                event_type='name_changed',
                old_value=instance._old_instance.name,
                new_value=instance.name
            )

@receiver(pre_delete, sender=SonarrInstance)
def sonarr_instance_deleted(sender, instance, **kwargs):
    InstanceChangeLog.objects.create(
        instance_type='sonarr',
        instance_id=instance.id,
        event_type='deleted',
        old_value=instance.name
    )

class Log(models.Model):
    id = models.BigAutoField(primary_key=True)
    date = models.DateTimeField()
    status = models.IntegerField()
    provider = models.IntegerField()
    text = models.TextField()
    
    class Meta:
        verbose_name_plural = "log"
        
    def __str__(self):
        return self.text