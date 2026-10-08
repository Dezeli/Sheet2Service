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
    managed = models.BooleanField(default=False)
    workflow_config = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ManagedRow(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="managed_rows")
    row_number = models.PositiveIntegerField()
    values = models.JSONField()

    class Meta:
        ordering = ["row_number"]
        constraints = [models.UniqueConstraint(fields=["upload", "row_number"], name="unique_managed_row_number")]


class FieldChoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="field_choices")
    column_number = models.PositiveSmallIntegerField()
    value = models.TextField()
    value_hash = models.CharField(max_length=64)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["column_number", "value"]
        constraints = [models.UniqueConstraint(fields=["upload", "column_number", "value_hash"], name="unique_field_choice_hash")]


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUBMITTED = "submitted", "Submitted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="service_requests")
    subject_row = models.ForeignKey(ManagedRow, null=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices)
    created_by_session = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


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
