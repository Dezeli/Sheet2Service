import uuid

from django.db import models


def original_path(instance, filename):
    return f"originals/{instance.id}/{instance.file_type}"


class Upload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(max_length=40, db_index=True)
    original_name = models.CharField(max_length=255)
    original = models.FileField(upload_to=original_path)
    file_type = models.CharField(max_length=4)
    size = models.PositiveIntegerField()
    encoding = models.CharField(max_length=16, blank=True)
    analysis = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ModelCall(models.Model):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="model_calls")
    purpose = models.TextField()
    provider = models.CharField(max_length=40, default="anthropic")
    model = models.CharField(max_length=100, db_index=True)
    request_body = models.JSONField()
    approval_note = models.TextField()
    approved_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.STARTED)
    response_body = models.TextField(blank=True)
    parsed_result = models.JSONField(null=True, blank=True)
    validation_error = models.TextField(blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    provider_request_id = models.CharField(max_length=255, blank=True)
    usage = models.JSONField(default=dict)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
