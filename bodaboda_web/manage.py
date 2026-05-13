#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env_file()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bodaboda_web.settings.dev')
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
