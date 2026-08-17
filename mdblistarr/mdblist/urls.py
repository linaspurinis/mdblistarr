from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', LoginView.as_view(template_name='login.html', redirect_authenticated_user=False), name='login'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('healthz', lambda request: JsonResponse({'status': 'ok'}), name='healthz'),
    path('', include('mdblistrr.urls')),
]
