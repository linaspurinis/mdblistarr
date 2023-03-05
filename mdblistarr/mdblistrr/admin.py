from django.contrib import admin
from .models import Preferences, Log

class PreferencesAdmin(admin.ModelAdmin):
    list_display = ("name", "value", )
    search_fields = ('name', 'value', )
admin.site.register(Preferences, PreferencesAdmin)

class LogAdmin(admin.ModelAdmin):
    list_display = ("date", "provider", "status", "text",  )
    search_fields = ('date', 'provider', 'status', )
admin.site.register(Log, LogAdmin)