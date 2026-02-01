#!/bin/bash
# Django
cp /usr/src/app/mdblist/urls.py.1 /usr/src/app/mdblist/urls.py
if [ "${RESET_DB}" = "1" ]; then
    rm -f /usr/src/db/db.sqlite3
fi
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc"  -delete
python /usr/src/app/manage.py makemigrations
python /usr/src/app/manage.py migrate
python /usr/src/app/manage.py shell << EOF
from django.contrib.auth.models import User;
if User.objects.filter(username = 'admin').first() is None:
    User.objects.create_superuser('admin', 'admin@mdblistarr', 'admin')
EOF
cp /usr/src/app/mdblist/urls.py.2 /usr/src/app/mdblist/urls.py
python /usr/src/app/manage.py run_task_scheduler &
python /usr/src/app/manage.py runserver 0.0.0.0:$PORT
exec "$@"
