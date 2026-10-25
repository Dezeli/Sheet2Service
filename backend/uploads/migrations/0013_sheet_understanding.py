import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('uploads', '0012_upload_field_labels'),
    ]

    operations = [
        migrations.AddField(model_name='upload', name='service_blueprint', field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='upload', name='understanding', field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='upload', name='understanding_overrides', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='managedrow', name='created_by_session',
                            field=models.CharField(blank=True, db_index=True, default='', max_length=40)),
        migrations.CreateModel(
            name='RowHistory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('flow_id', models.CharField(max_length=32)),
                ('from_state', models.CharField(blank=True, max_length=48)),
                ('to_state', models.CharField(max_length=48)),
                ('actor', models.CharField(max_length=16)),
                ('session_key', models.CharField(blank=True, max_length=40)),
                ('changes', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('row', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='uploads.managedrow')),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
