from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import DriverDocument
from core.views import _clamav_scan


class Command(BaseCommand):
    help = 'Scan pending driver documents with ClamAV and update scan status.'

    def handle(self, *args, **options):
        pending = DriverDocument.objects.filter(scan_status=DriverDocument.ScanStatus.PENDING)[:50]
        scanned = 0
        for doc in pending:
            try:
                _clamav_scan(doc.file)
                doc.scan_status = DriverDocument.ScanStatus.CLEAN
                doc.scan_message = ''
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if 'Malware detected' in message:
                    doc.scan_status = DriverDocument.ScanStatus.INFECTED
                else:
                    doc.scan_status = DriverDocument.ScanStatus.ERROR
                doc.scan_message = message[:255]
            doc.scanned_at = timezone.now()
            doc.save(update_fields=['scan_status', 'scan_message', 'scanned_at'])
            if doc.scan_status == DriverDocument.ScanStatus.INFECTED:
                doc.file.delete(save=False)
            scanned += 1

        self.stdout.write(self.style.SUCCESS(f'Scanned {scanned} driver documents.'))
