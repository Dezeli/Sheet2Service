from django.db import migrations

from uploads.personas import standard_personas


def split_roles(apps, schema_editor):
    """Services built before the roles were fixed get the same non-overlapping set new ones get."""
    Upload = apps.get_model("uploads", "Upload")
    for upload in Upload.objects.exclude(service_config=None).only("service_config"):
        config = upload.service_config or {}
        personas = config.get("personas") or []
        if not any(persona.get("id") == "booker" for persona in personas):
            continue  # record-only sheets keep their viewer and admin
        booking = config.get("booking") or {}
        config["personas"] = standard_personas(personas, config.get("columnRoles") or [], booking.get("states") or [],
                                               accepts_bookings=booking.get("mode") != "none")
        upload.service_config = config
        upload.save(update_fields=["service_config"])


class Migration(migrations.Migration):
    dependencies = [("uploads", "0020_inquiry_board")]
    operations = [migrations.RunPython(split_roles, migrations.RunPython.noop)]
