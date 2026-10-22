import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('uploads', '0012_upload_field_labels')]

    operations = [
        migrations.AddField(
            model_name='upload', name='service_blueprint',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='BlueprintSubmission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('workflow_id', models.CharField(max_length=32)),
                ('subject_snapshot', models.TextField()),
                ('values', models.JSONField(default=dict)),
                ('status', models.CharField(max_length=32)),
                ('workflow_snapshot', models.JSONField()),
                ('created_by_session', models.CharField(db_index=True, max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subject_row', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='uploads.managedrow')),
                ('upload', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blueprint_submissions', to='uploads.upload')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
    ]
