from django.shortcuts import render
from .models import Log

def log_view(request):
    logs = Log.objects.filter().order_by('-date')[:200]
    return render(request, "log.html", {'logs': logs, })

