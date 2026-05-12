release: cd bodaboda_web && python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear
web: cd bodaboda_web && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers=${WEB_CONCURRENCY:-2} --timeout 120 --access-logfile - --error-logfile - bodaboda_web.wsgi:application

