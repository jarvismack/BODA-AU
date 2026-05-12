# BodaBoda Render Deployment Guide

## ✅ What Was Fixed

1. **WSGI Module Path** - Fixed incorrect path in `bodaboda_web/wsgi.py`
   - ❌ Was: `bodaboda_web.bodaboda_web.settings.prod` 
   - ✅ Now: `bodaboda_web.settings.prod`

2. **Deployment Files** - Created at repository root:
   - `Procfile` - Defines release and web process commands
   - `render.yaml` - Render-specific configuration
   - `runtime.txt` - Python version specification
   - `build.sh` - Build script
   - `.renderignore` - Optimization file
   - `requirements.txt` - Dependencies at root level

3. **Django Settings** - Production settings now:
   - Handle missing SECRET_KEY gracefully with fallback
   - Support both PostgreSQL and SQLite databases
   - Work with Render's proxy infrastructure
   - Properly set SSL redirect, HSTS, and security headers

4. **Middleware** - WhiteNoiseMiddleware properly configured for static files

## 🚀 Deploying to Render

### Step 1: Push Changes to GitHub
```bash
git add -A
git commit -m "Fix Render deployment configuration"
git push origin main
```

### Step 2: Create Render Service
1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select the BodaBoda repository

### Step 3: Configure Environment Variables
Go to the environment variables section and set:

#### Required for Initial Deployment:
```
DEBUG=0
DJANGO_SETTINGS_MODULE=bodaboda_web.settings.prod
PYTHONUNBUFFERED=1
PORT=8000
```

#### Security (Generate these values):
```
SECRET_KEY=your-50-character-random-key-here
```

To generate a secure SECRET_KEY:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

#### For Your Domain:
```
ALLOWED_HOSTS=your-app.onrender.com,www.your-app.onrender.com
```

#### Optional - For PostgreSQL (Recommended):
```
DB_ENGINE=django.db.backends.postgresql
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host.postgres.render.com
DB_PORT=5432
DB_CONN_MAX_AGE=60
```

#### Optional - For Email (OTP/Password Reset):
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

#### Optional - For SMS (Twilio):
```
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890
```

### Step 4: Configure Build Settings
- **Build Command**: `cd bodaboda_web && python manage.py collectstatic --noinput && python manage.py migrate`
- **Start Command**: `cd bodaboda_web && gunicorn bodaboda_web.wsgi:application --log-file - --access-logfile -`

### Step 5: Deploy
Click "Deploy" and monitor the logs for any errors.

## 🔍 Troubleshooting

### If deployment fails with "exit status 1":

1. **Check Logs** - Click "Logs" in Render dashboard
2. **Common issues:**
   - Missing SECRET_KEY → Add to environment variables
   - Database connection error → Check DB credentials
   - Static files error → Check STATIC_ROOT path
   - Import errors → Check for syntax errors in settings

### To view production logs:
```bash
# In Render dashboard, click the service → Logs
```

### To run commands on Render:
```bash
# Connect shell (if available)
python manage.py createsuperuser
python manage.py shell
```

## 📝 Important Notes

1. **Static Files**: WhiteNoiseMiddleware automatically serves static files in production
2. **Database**: First deployment uses SQLite, switch to PostgreSQL for production
3. **Secret Key**: Change to a real 50+ character key in production
4. **SSL**: Automatically enabled with Render's SSL certificate
5. **Media Files**: Store files in `/media/` directory (not persistent on Render - use external storage for production)

## 🔐 Production Checklist

- [ ] SECRET_KEY set to a strong, random value
- [ ] DEBUG set to 0
- [ ] ALLOWED_HOSTS configured correctly
- [ ] Database configured (PostgreSQL recommended)
- [ ] Email backend configured
- [ ] SMS provider configured (if using Twilio)
- [ ] Static files collected and serving
- [ ] SSL certificate valid
- [ ] HSTS preload tested
- [ ] Admin panel accessible

## 📞 Support

For Render support: https://render.com/docs/troubleshooting-deploys
For Django support: https://docs.djangoproject.com/

---
Last Updated: 2026-05-12
