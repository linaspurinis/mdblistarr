#!/bin/bash
set -euo pipefail

# Django
python /usr/src/app/mdblistrr/runtime_secrets.py

cp /usr/src/app/mdblist/urls.py.1 /usr/src/app/mdblist/urls.py
if [ "${RESET_DB:-}" = "1" ]; then
    rm -f /usr/src/db/db.sqlite3
fi
python /usr/src/app/manage.py reconcile_migrations
python /usr/src/app/manage.py migrate
python /usr/src/app/manage.py encrypt_secrets
python /usr/src/app/manage.py secure_startup
cp /usr/src/app/mdblist/urls.py.2 /usr/src/app/mdblist/urls.py

python /usr/src/app/manage.py run_task_scheduler &
python /usr/src/app/manage.py runserver 0.0.0.0:$PORT
exec "$@"
