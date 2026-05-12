import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application

# Add the current directory to sys.path so Django can find 'core' and other apps
current_dir = Path(__file__).resolve().parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'bodaboda_web.settings.prod'
)

application = get_wsgi_application()