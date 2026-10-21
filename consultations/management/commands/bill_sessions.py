import time

from django.core.management.base import BaseCommand

from consultations.services import bill_active_sessions


class Command(BaseCommand):
    help = "Bill all in-progress sessions. Use --interval to keep running."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=0, help="seconds between runs (0 = run once)")

    def handle(self, *args, interval, **options):
        while True:
            count = bill_active_sessions()
            self.stdout.write(f"billed {count} active session(s)")
            if not interval:
                break
            time.sleep(interval)
