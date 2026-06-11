from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Create or reuse an API token for Postman/testing."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-password-change-me")
        parser.add_argument("--email", default="demo@example.com")

    def handle(self, *args, **options):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"],
            defaults={"email": options["email"]},
        )
        if created:
            user.set_password(options["password"])
            user.save(update_fields=["password"])

        token, _ = Token.objects.get_or_create(user=user)
        self.stdout.write(self.style.SUCCESS(f"Token {token.key}"))
