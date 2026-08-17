from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from mdblistrr.crypto import SecretDecryptionError, decrypt, encrypt, get_fernet, is_encrypted
from mdblistrr.models import Preferences, RadarrInstance, SonarrInstance

class Command(BaseCommand):
    help = "Validate encrypted secrets and encrypt plaintext application secrets in-place. Idempotent."

    def _validate_or_encrypt(self, value):
        if value in (None, ""):
            return value, False
        if is_encrypted(value):
            decrypt(value)  # authenticate existing ciphertext with the configured key
            return value, False
        return encrypt(value), True

    def handle(self, *args, **options):
        try:
            get_fernet()  # fail immediately if missing or malformed
            changed = 0
            with transaction.atomic():
                for model, field in [(RadarrInstance, 'apikey'), (SonarrInstance, 'apikey')]:
                    table = model._meta.db_table
                    with connection.cursor() as c:
                        c.execute(f"SELECT id, {field} FROM {table}")
                        for pk, value in c.fetchall():
                            new_value, did_change = self._validate_or_encrypt(value)
                            if did_change:
                                c.execute(f"UPDATE {table} SET {field}=%s WHERE id=%s", [new_value, pk])
                                changed += 1
                with connection.cursor() as c:
                    c.execute("SELECT id, name, value FROM mdblistrr_preferences")
                    for pk, name, value in c.fetchall():
                        if name in Preferences.secret_names():
                            new_value, did_change = self._validate_or_encrypt(value)
                            if did_change:
                                c.execute("UPDATE mdblistrr_preferences SET value=%s WHERE id=%s", [new_value, pk])
                                changed += 1
        except SecretDecryptionError as exc:
            raise CommandError("Stored encrypted secret could not be authenticated with the configured encryption key.") from exc
        except Exception as exc:
            raise CommandError("Secret encryption startup validation failed.") from exc
        self.stdout.write(f"Encrypted and validated application secrets ({changed} plaintext value(s) updated).")
