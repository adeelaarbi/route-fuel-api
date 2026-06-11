from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.fuel.models import FuelStation

REQUIRED_COLUMNS = {
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
}


class Command(BaseCommand):
    help = "Import fuel station prices from the assignment CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument("--truncate", action="store_true", help="Delete existing fuel stations first.")

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file does not exist: {csv_path}")

        if options["truncate"]:
            FuelStation.objects.all().delete()
            self.stdout.write(self.style.WARNING("Deleted existing fuel stations."))

        created = 0
        updated = 0
        skipped = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as file_obj:
            reader = csv.DictReader(file_obj)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"CSV is missing required columns: {sorted(missing)}")

            with transaction.atomic():
                for row_number, row in enumerate(reader, start=2):
                    try:
                        opis_id = int(row["OPIS Truckstop ID"])
                        rack_id = int(row["Rack ID"])
                        retail_price = Decimal(row["Retail Price"]).quantize(Decimal("0.0001"))
                    except (ValueError, InvalidOperation) as exc:
                        skipped += 1
                        self.stderr.write(f"Skipping row {row_number}: {exc}")
                        continue

                    defaults = {
                        "retail_price": retail_price,
                        "source_file": csv_path.name,
                    }
                    station, was_created = FuelStation.objects.update_or_create(
                        opis_truckstop_id=opis_id,
                        name=row["Truckstop Name"].strip(),
                        address=row["Address"].strip(),
                        city=row["City"].strip(),
                        state=row["State"].strip(),
                        rack_id=rack_id,
                        defaults=defaults,
                    )
                    created += int(was_created)
                    updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import completed. created={created}, updated={updated}, skipped={skipped}"
            )
        )
