from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Create a local database backup for production recovery.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            dest='output_dir',
            default='',
            help='Optional backup directory override. Defaults to BACKUP_DIR from settings.',
        )

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'] or settings.BACKUP_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        engine = connection.settings_dict.get('ENGINE', '')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if engine.endswith('sqlite3'):
            source = Path(connection.settings_dict['NAME'])
            if not source.exists():
                raise CommandError(f'SQLite database not found: {source}')
            target = output_dir / f'db_{timestamp}.sqlite3'
            shutil.copy2(source, target)
            self.stdout.write(self.style.SUCCESS(f'SQLite backup created: {target}'))
            return

        if 'postgresql' in engine:
            db_name = connection.settings_dict.get('NAME', '')
            db_user = connection.settings_dict.get('USER', '')
            db_host = connection.settings_dict.get('HOST', '')
            db_port = str(connection.settings_dict.get('PORT', '5432') or '5432')
            db_password = connection.settings_dict.get('PASSWORD', '')
            if not db_name:
                raise CommandError('Database NAME is required for PostgreSQL backup.')

            target = output_dir / f'db_{timestamp}.sql'
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password

            cmd = [
                'pg_dump',
                '-h',
                db_host or '127.0.0.1',
                '-p',
                db_port,
                '-U',
                db_user,
                '-f',
                str(target),
                db_name,
            ]
            try:
                subprocess.run(cmd, env=env, check=True)
            except FileNotFoundError as exc:
                raise CommandError('pg_dump is not installed or not available on PATH.') from exc
            except subprocess.CalledProcessError as exc:
                raise CommandError(f'pg_dump failed with exit code {exc.returncode}') from exc

            self.stdout.write(self.style.SUCCESS(f'PostgreSQL backup created: {target}'))
            return

        raise CommandError(f'Unsupported database engine for backup: {engine}')
