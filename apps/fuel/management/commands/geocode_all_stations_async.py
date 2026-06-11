from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.fuel.tasks import geocode_all_stations_task


class Command(BaseCommand):
    help = "Queue a Celery job that geocodes fuel stations missing coordinates."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--sleep-seconds", type=float, default=0.25)

    def handle(self, *args, **options):
        task = geocode_all_stations_task.delay(
            batch_size=options["batch_size"],
            sleep_seconds=options["sleep_seconds"],
        )
        self.stdout.write(self.style.SUCCESS(f"Queued station geocoding task_id={task.id}"))
