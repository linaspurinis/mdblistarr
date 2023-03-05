#!/bin/bash
# Cron
/usr/sbin/cron -l 2
# Django
cp /usr/src/app/mdblist/urls.py.1 /usr/src/app/mdblist/urls.py
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
python /usr/src/app/manage.py crontab add
python /usr/src/app/manage.py runserver 0.0.0.0:$PORT
exec "$@"
