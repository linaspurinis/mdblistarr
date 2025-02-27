from django.urls import path
from .views import home_view
from . import views
from .cron import post_radarr_payload
from .log import log_view

urlpatterns = [
    path('', home_view, name='home_view'),
    path('log', log_view, name='log_view'),
    # URLs for AJAX test connection endpoints
    path('test_radarr_connection/', views.test_radarr_connection, name='test_radarr_connection'),
    path('test_sonarr_connection/', views.test_sonarr_connection, name='test_sonarr_connection'),    
]