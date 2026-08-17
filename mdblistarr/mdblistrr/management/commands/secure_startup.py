from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from mdblistrr.crypto import read_secret
from mdblistrr.admin_state import usable_administrator_exists

class Command(BaseCommand):
    help = "Bootstrap secure admin credentials and disable legacy admin/admin."

    def handle(self, *args, **options):
        User = get_user_model()
        username = read_secret("MDBLISTARR_ADMIN_USERNAME") or "admin"
        password = read_secret("MDBLISTARR_ADMIN_PASSWORD")
        with transaction.atomic():
            legacy = User.objects.filter(username="admin", is_active=True).first()
            if legacy and legacy.check_password("admin"):
                legacy.is_active = False
                legacy.set_unusable_password()
                legacy.save(update_fields=["is_active", "password"])
                self.stdout.write("Disabled legacy insecure admin account.")
            if not usable_administrator_exists():
                if not password:
                    self.stdout.write("No usable administrator exists; first-run web setup is required.")
                    return
                user = User.objects.filter(username=username).first()
                if user:
                    user.set_password(password)
                    user.is_staff = True; user.is_superuser = True; user.is_active = True
                    user.save()
                    self.stdout.write(f"Secured existing administrator '{username}'.")
                else:
                    User.objects.create_superuser(username=username, password=password)
                    self.stdout.write(f"Created initial administrator '{username}'.")
            else:
                self.stdout.write("Active staff administrator already exists; not changing passwords.")
