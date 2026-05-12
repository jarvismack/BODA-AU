release: cd bodaboda_web && python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear
web: cd bodaboda_web && gunicorn bodaboda_web.wsgi:application --log-file - --access-logfile - --workers=${WEB_CONCURRENCY:-2} --timeout 120 --bind 0.0.0.0:${PORT:-8000}

