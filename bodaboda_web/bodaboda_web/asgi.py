import os
import sys
from pathlib import Path

from django.core.asgi import get_asgi_application

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]


def ensure_path(path: Path) -> None:
    resolved = str(path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


# ASGI servers may start outside the Django project directory, so make both
# the Django app root and repository root importable before loading settings.
ensure_path(BASE_DIR)
ensure_path(REPO_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bodaboda_web.settings.prod')

application = get_asgi_application()
