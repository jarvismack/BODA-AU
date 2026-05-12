# Environment Variables Setup for Render Deployment

## ✅ Minimum Required Variables (Already Set)

| Variable | Current Value | Purpose |
|----------|---------------|---------|
| `DEBUG` | `0` | Disables debug mode in production |
| `SECRET_KEY` | ✅ Set (64 chars) | Django secret key for security |
| `ALLOWED_HOSTS` | ✅ Set with Render domain | Hosts allowed to serve the app |
| `DJANGO_SETTINGS_MODULE` | `bodaboda_web.settings.prod` | Use production settings |
| `PYTHONUNBUFFERED` | `1` | Real-time logging in production |
| `PORT` | `8000` | Application port |

## 🔐 Security Settings (Configured)

```
USE_X_FORWARDED_HOST=1              # Trust Render's proxy headers
SECURE_SSL_REDIRECT=1               # Redirect HTTP to HTTPS
SESSION_COOKIE_SECURE=1             # Only send cookies over HTTPS
CSRF_COOKIE_SECURE=1                # CSRF cookies only over HTTPS
SECURE_HSTS_SECONDS=31536000        # HSTS header (1 year)
SECURE_HSTS_INCLUDE_SUBDOMAINS=1    # Include subdomains in HSTS
SECURE_HSTS_PRELOAD=0               # Set to 1 after domain submitted
TRUST_X_FORWARDED_FOR=1             # Trust proxy's X-Forwarded-For
```

## 📊 Current Database Configuration

**Current (Local PostgreSQL):**
```
DB_ENGINE=django.db.backends.postgresql
DB_NAME=bodaboda
DB_USER=bodaboda_user
DB_PASSWORD=Lenoveclear
DB_HOST=127.0.0.1
DB_PORT=5432
```

**For Render Deployment:**
Option 1: Create PostgreSQL add-on on Render and update above credentials
Option 2: Keep SQLite for free plan (auto-configured as fallback)

## 📧 Email Configuration (Already Set)

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=mcdonaldzizu28@gmail.com
EMAIL_HOST_PASSWORD=lldhjjegfyuhoiae
EMAIL_USE_TLS=1
```

## 📱 SMS Configuration

```
SMS_PROVIDER=console    # Currently just logs to console
# Set to 'twilio' and configure credentials to enable real SMS:
# TWILIO_ACCOUNT_SID=your_sid
# TWILIO_AUTH_TOKEN=your_token
# TWILIO_FROM_NUMBER=+1234567890
```

## 🚀 Next Steps for Render

1. **Add Database (Optional but Recommended)**
   - Go to Render dashboard → Add PostgreSQL
   - Copy credentials into environment variables
   - Update `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

2. **Deploy on Render**
   ```bash
   # Push code with updated .env
   git add -A
   git commit -m "Setup Render environment variables"
   git push origin main
   ```

3. **Set Render Environment Variables**
   - Go to Render dashboard → Services → Your app → Environment
   - Add/override these key variables:
     - `DEBUG=0`
     - `SECRET_KEY=gytMEzYIqtC7Wmc7uUVgXwREIofYBPzd5P4O1ZxDlkP1nm0bEx1SQQxvaIx8i-qV9uuyriNcWVzaNetzoWO96g`
     - `ALLOWED_HOSTS=your-render-domain.onrender.com`
     - If using Render PostgreSQL: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

4. **Trigger Deployment**
   - Render automatically deploys on push
   - Monitor logs for errors

## ✔️ Validation

All configurations have been tested locally:
```
✅ Django system checks passed (0 issues)
✅ WSGI module correctly configured
✅ Procfile properly configured
✅ Requirements.txt complete
✅ render.yaml valid
✅ Static files handler configured (WhiteNoiseMiddleware)
✅ Security headers configured
```

## 📝 Important Notes

- **Secret Key**: Currently set and sufficient. For production, generate a new one:
  ```bash
  python manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```

- **Media Files**: Stored in `/media/` (not persistent on free Render plan)
  - For production, configure external storage (AWS S3, etc.)

- **Database**: 
  - Free plan recommended for testing
  - Use Render PostgreSQL add-on for production

---
**Setup Date**: 2026-05-12  
**Status**: ✅ Ready for Render Deployment
