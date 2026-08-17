from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlparse
from .admin_state import usable_administrator_exists

def _json_request(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or 'application/json' in request.headers.get('accept','')

class StaffRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        path = request.path_info
        login_url = reverse('login')
        setup_url = reverse('setup')
        public = (login_url, setup_url, '/healthz')
        static_path = urlparse(settings.STATIC_URL).path or settings.STATIC_URL
        if not static_path.startswith('/'):
            static_path = '/' + static_path
        if not static_path.endswith('/'):
            static_path += '/'
        if path.startswith(static_path) or path in public:
            if path == login_url and not usable_administrator_exists():
                return redirect('setup')
            return self.get_response(request)
        if not usable_administrator_exists():
            if _json_request(request):
                return JsonResponse({'detail':'Initial setup is required.'}, status=503)
            return redirect('setup')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            if _json_request(request):
                return JsonResponse({'detail':'Authentication required.'}, status=401)
            return redirect(f"{login_url}?next={request.get_full_path()}")
        if not (user.is_active and (user.is_staff or user.is_superuser)):
            if _json_request(request):
                return JsonResponse({'detail':'Staff access required.'}, status=403)
            return redirect('login')
        return self.get_response(request)
