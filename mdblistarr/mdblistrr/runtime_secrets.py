import errno
import os
import secrets
import string
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
try:
    from django.core.exceptions import ImproperlyConfigured
except Exception:
    class ImproperlyConfigured(Exception):
        pass

DEFAULT_SECRET_DIR = Path(os.environ.get('MDBLISTARR_SECRET_DIR', '/usr/src/db/secrets'))
DEFAULT_SECRET_FILES = {
    'DJANGO_SECRET_KEY': DEFAULT_SECRET_DIR / 'django_secret_key',
    'MDBLISTARR_ENCRYPTION_KEY': DEFAULT_SECRET_DIR / 'mdblistarr_encryption_key',
}

class SecretResolutionError(ImproperlyConfigured):
    pass

def _django_key():
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(chars) for _ in range(50))

def _validate(name, value):
    if not value:
        raise SecretResolutionError(f'{name} is empty or invalid.')
    if name == 'MDBLISTARR_ENCRYPTION_KEY':
        try:
            Fernet(value.encode('utf-8'))
        except Exception as exc:
            raise SecretResolutionError(f'{name} is empty or invalid.') from exc
    return value

def _read_file(path, name, source):
    try:
        value = Path(path).read_text(encoding='utf-8').rstrip('\r\n')
    except OSError as exc:
        raise SecretResolutionError(f'Unable to read {source} for {name}.') from exc
    return _validate(name, value)

def _cleanup_tmp(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass

def _atomic_create(path, value):
    """Publish a newly-generated secret with strict no-clobber semantics.

    The Docker target is Linux, where hard-linking a fully-written temp file to
    the destination is atomic and fails with EEXIST if another process wins the
    race. Do not fall back to os.replace(): replacing a persistent encryption key
    would be worse than failing startup.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(value + '\n')
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return False
            raise SecretResolutionError('Unable to safely create persistent secret file without overwrite support.') from exc
        return True
    finally:
        _cleanup_tmp(tmp)

def resolve_secret(name, file_env=None, required=False, default_path=None, generate=False):
    file_env = file_env or f'{name}_FILE'
    explicit_file = os.environ.get(file_env)
    if explicit_file:
        return _read_file(explicit_file, name, file_env)
    env_value = os.environ.get(name)
    if env_value:
        return _validate(name, env_value)
    path = Path(default_path or DEFAULT_SECRET_FILES.get(name, '')) if (default_path or name in DEFAULT_SECRET_FILES) else None
    if path and path.exists():
        return _read_file(path, name, 'persistent secret file')
    if generate and path:
        value = Fernet.generate_key().decode('ascii') if name == 'MDBLISTARR_ENCRYPTION_KEY' else _django_key()
        _atomic_create(path, value)
        return _read_file(path, name, 'persistent secret file')
    if required:
        raise SecretResolutionError(f'{name} or {file_env} must be configured.')
    return ''

def bootstrap_runtime_secrets():
    for name in ('DJANGO_SECRET_KEY', 'MDBLISTARR_ENCRYPTION_KEY'):
        value = resolve_secret(name, required=True, generate=True)
        os.environ[name] = value

def main():
    bootstrap_runtime_secrets()
    print('MDBListarr runtime secrets are configured.')

if __name__ == '__main__':
    main()
