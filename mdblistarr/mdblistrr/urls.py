from django.urls import path
from .views import home_view
from . import views
from .log import log_view

urlpatterns = [
    path('setup/', views.setup_view, name='setup'),
    path('', home_view, name='home_view'),
    path('log', log_view, name='log_view'),
    path('test_radarr_connection/', views.test_radarr_connection, name='test_radarr_connection'),
    path('test_sonarr_connection/', views.test_sonarr_connection, name='test_sonarr_connection'),
    path('test_plex_connection/', views.test_plex_connection, name='test_plex_connection'),
    path('set_active_tab/', views.set_active_tab, name='set_active_tab'),
    path('oauth/device/start', views.oauth_device_start, name='oauth_device_start'),
    path('oauth/device/poll', views.oauth_device_poll, name='oauth_device_poll'),
    path('oauth/disconnect', views.oauth_disconnect, name='oauth_disconnect'),
    path('plex/auth/start', views.plex_auth_start, name='plex_auth_start'),
    path('plex/auth/poll', views.plex_auth_poll, name='plex_auth_poll'),
    path('plex/sync/start', views.plex_sync_start, name='plex_sync_start'),
    path('plex/reset/start', views.plex_reset_start, name='plex_reset_start'),
    path('plex/sync/status', views.plex_sync_status, name='plex_sync_status'),
    path('plex/sync/cancel', views.plex_sync_cancel, name='plex_sync_cancel'),
]
