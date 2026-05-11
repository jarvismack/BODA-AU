# Zanzibar Bodaboda Web App (Django)

Fresh web-based MVP built with Django backend + HTML/CSS/JavaScript frontend.

## Features
- Role-based accounts: Passenger, Driver, Admin
- Passenger: find nearby drivers, request ride, view current ride and history
- Driver: create profile, go online/offline, manage ride lifecycle, view earnings
- Admin: view and verify drivers
- Fare calculation:
  - Motorcycle: `1500 + distance_km * 700`
  - Bajaji: `2500 + distance_km * 700`

## Project Structure
- `bodaboda_web/` Django project
- `core/models.py` domain models
- `core/views.py` auth + role-based JSON APIs + page rendering
- `core/templates/` HTML pages
- `core/static/js/` frontend logic

## Run Locally
1. Install dependencies
```bash
cd "bodaboda_web"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Apply migrations
```bash
python manage.py migrate
```

3. Create admin user
```bash
python manage.py createsuperuser
```

4. Start server
```bash
python manage.py runserver
```

5. Open app
- Main app: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`

## Security-Ready Configuration
1. Copy env template:
```bash
cd "bodaboda_web"
cp -n .env.example .env
```
2. Edit `.env` and set at least:
- `DEBUG=0`
- `SECRET_KEY` (long random value)
- `ALLOWED_HOSTS` with your ngrok host
- `CSRF_TRUSTED_ORIGINS` with your ngrok https URL

3. Validate deploy checks:
```bash
.venv/bin/python manage.py check --deploy
```

## Temporary Ngrok Test
1. Start Django:
```bash
cd "bodaboda_web"
.venv/bin/python manage.py runserver 0.0.0.0:8000
```
2. Start ngrok tunnel:
```bash
ngrok http 8000
```
3. Put the ngrok hostname into `.env`:
- `ALLOWED_HOSTS=...,your-subdomain.ngrok-free.app`
- `CSRF_TRUSTED_ORIGINS=https://your-subdomain.ngrok-free.app`

## Usage Notes
- Register passenger and driver accounts from homepage.
- Driver must save profile first.
- Admin verifies driver via dashboard (login as superuser or admin-role user).
- Verified driver goes online to receive ride requests.

## Security Defaults Included
- CSRF middleware enabled for all POST requests
- Django auth password hashing
- Login session handling with secure cookie flags
- Input validation + error handling in backend endpoints

## SMS Notifications
Notifications are triggered for:
- Passenger after registration
- Driver after registration
- Driver after admin verification

By default notifications run in simulated mode and are saved to `NotificationLog` in Django admin.

To send real SMS with Twilio, set environment variables before running:
```bash
export SMS_PROVIDER=twilio
export TWILIO_ACCOUNT_SID=your_sid
export TWILIO_AUTH_TOKEN=your_auth_token
export TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```
