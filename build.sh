#!/bin/bash
set -e  # Exit on any error

echo "=== BodaBoda Render Deployment Build Script ==="

# Set environment
export DJANGO_SETTINGS_MODULE=bodaboda_web.settings.prod
export PYTHONUNBUFFERED=1

# Change to Django project directory
cd bodaboda_web

echo "✓ Environment variables set"
echo "✓ Working directory: $(pwd)"

# Install dependencies (already done by Render, but ensuring)
echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1 || true

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear 2>&1

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput 2>&1

echo "✓ Build completed successfully!"
