# models.py
from django.db import models

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