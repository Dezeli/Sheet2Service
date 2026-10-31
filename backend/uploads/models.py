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
    understanding = models.JSONField(null=True, blank=True)
    service_config = models.JSONField(null=True, blank=True)
    field_labels = models.JSONField(default=dict, blank=True)
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


class Inquiry(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="inquiries")
    subject_row = models.ForeignKey(ManagedRow, null=True, blank=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField(blank=True)
    title = models.CharField(max_length=120)
    body = models.TextField()
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    created_by_session = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Notice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="notices")
    title = models.CharField(max_length=120)
    body = models.TextField()
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Resource(models.Model):
    """Something that can be reserved: a room, a device, a course, a court. Nested by level."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="resources")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    level = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=300)
    path = models.TextField(db_index=True)  # "기관명 / 상품명" for lookups and sorting
    source_row = models.ForeignKey(ManagedRow, null=True, blank=True, on_delete=models.SET_NULL)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)  # label -> value from the sheet
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["path"]
        constraints = [models.UniqueConstraint(fields=["upload", "path"], name="unique_resource_path")]


class Slot(models.Model):
    """A bookable occurrence of a resource: a date, a time range or a labelled time slot."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="slots")
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.CASCADE, related_name="slots")
    date = models.DateField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    time_slot = models.CharField(max_length=120, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    imported_count = models.PositiveIntegerField(default=0)  # attendance already recorded on the sheet
    source_row = models.ForeignKey(ManagedRow, null=True, blank=True, on_delete=models.SET_NULL)
    closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "starts_at", "time_slot", "id"]


class Booking(models.Model):
    class Kind(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        IN_USE = "in_use", "In use"
        COMPLETED = "completed", "Completed"
        WAITING = "waiting", "Waiting"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="bookings")
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    slot = models.ForeignKey(Slot, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    source_row = models.ForeignKey(ManagedRow, null=True, blank=True, on_delete=models.SET_NULL)
    booker = models.CharField(max_length=200, blank=True)
    created_by_session = models.CharField(max_length=40, blank=True, db_index=True)
    party_size = models.PositiveIntegerField(null=True, blank=True)
    date = models.DateField(null=True, blank=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    time_slot = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=Kind.choices, default=Kind.REQUESTED, db_index=True)
    status_label = models.CharField(max_length=120, blank=True)  # the sheet's own wording
    purpose = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payment = models.CharField(max_length=120, blank=True)
    staff = models.CharField(max_length=200, blank=True)
    organization = models.CharField(max_length=200, blank=True)
    attributes = models.JSONField(default=dict, blank=True)  # booker attributes and other kept columns
    processing_note = models.TextField(blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)  # the sheet's own 등록·신청 일시
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at", "-id"]


class BookingEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    persona = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


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
