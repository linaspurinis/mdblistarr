from django.contrib.auth import get_user_model

def usable_administrator_queryset():
    return get_user_model().objects.filter(is_active=True, is_staff=True, is_superuser=True)

def usable_administrator_exists():
    return any(user.has_usable_password() for user in usable_administrator_queryset())
