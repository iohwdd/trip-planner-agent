from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from planner.services.planner_service import planner_service


class Command(BaseCommand):
    help = "Run the planning worker. Uses Redis queueing when available, with DB fallback."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process available jobs once and exit.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum jobs to process per polling cycle.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Polling interval in seconds for long-running mode.",
        )

    def handle(self, *args, **options):
        once = options["once"]
        limit = options["limit"]
        sleep_seconds = options["sleep"]

        if once:
            processed = planner_service.process_pending_jobs(limit=limit)
            self.stdout.write(self.style.SUCCESS(f"Processed {processed} job(s)."))
            return

        self.stdout.write(self.style.SUCCESS("Planning worker started."))
        while True:
            processed = planner_service.process_pending_jobs(limit=limit)
            if processed == 0:
                time.sleep(sleep_seconds)
