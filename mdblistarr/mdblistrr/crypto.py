import os
from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured
from .runtime_secrets import resolve_secret

PREFIX = "mdblistarr:v1:fernet:"
SECRET_PREF_NAMES = {"mdblist_apikey", "mdblist_access_token", "mdblist_refresh_token"}

class SecretDecryptionError(RuntimeError):
    pass

def read_secret(name, file_name=None, required=False):
    return resolve_secret(name, file_env=file_name, required=required)

def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)

_fernet = None

def get_fernet():
    global _fernet
    if _fernet is None:
        key = read_secret("MDBLISTARR_ENCRYPTION_KEY", required=True)
        try:
            _fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise ImproperlyConfigured("MDBLISTARR_ENCRYPTION_KEY must be a valid Fernet key.") from exc
    return _fernet

def encrypt(value):
    if value is None or value == "" or is_encrypted(value):
        return value
    token = get_fernet().encrypt(str(value).encode("utf-8")).decode("ascii")
    return PREFIX + token

def decrypt(value):
    if value is None or value == "" or not is_encrypted(value):
        return value
    token = value[len(PREFIX):]
    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretDecryptionError("Stored encrypted secret could not be decrypted with the configured key.") from exc
