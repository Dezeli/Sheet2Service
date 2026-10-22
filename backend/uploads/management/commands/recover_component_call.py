"""Recover one logged component-decision validation failure without a provider call."""

from django.core.management.base import BaseCommand, CommandError

from uploads.component_recovery import recover_failed_component_call


class Command(BaseCommand):
    help = "Revalidate one historical overlap error offline and record its component candidates."

    def add_arguments(self, parser):
        parser.add_argument("call_id")

    def handle(self, *args, **options):
        try:
            ids = recover_failed_component_call(options["call_id"])
        except (ValueError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("Recovered candidate IDs: " + ", ".join(map(str, ids)))
