# models.py
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save, pre_delete

class Preferences(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    value = models.CharField(max_length=255, null=True)
    
    class Meta:
        verbose_name_plural = "preferences"
        
    def __str__(self):
        return self.name

class RadarrInstance(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    apikey = models.CharField(max_length=255)
    quality_profile = models.CharField(max_length=255)
    root_folder = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class SonarrInstance(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    apikey = models.CharField(max_length=255)
    quality_profile = models.CharField(max_length=255)
    root_folder = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

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