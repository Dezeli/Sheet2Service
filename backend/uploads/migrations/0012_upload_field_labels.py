from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("uploads", "0011_quoterequest")]
    operations = [migrations.AddField(
        model_name="upload", name="field_labels", field=models.JSONField(blank=True, default=dict),
    )]
