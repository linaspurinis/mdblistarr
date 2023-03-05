from django.urls import path
from .views import home_view
from .cron import post_radarr_payload
from .log import log_view

urlpatterns = [
    path('', home_view, name='home_view'),
    path('log', log_view, name='log_view'),
]