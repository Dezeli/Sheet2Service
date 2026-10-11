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
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="service_requests")
    subject_row = models.ForeignKey(ManagedRow, null=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField()
    content = models.TextField(blank=True)
    processing_note = models.TextField(blank=True)
    approval_mode = models.CharField(max_length=8, choices=[("required", "Required"), ("none", "None")], default="required")
    status = models.CharField(max_length=16, choices=Status.choices)
    created_by_session = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


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


class QuoteRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUOTED = "quoted", "Quoted"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        UNAVAILABLE = "unavailable", "Unavailable"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="quote_requests")
    subject_row = models.ForeignKey(ManagedRow, null=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField()
    content = models.TextField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=[(value, value) for value in ("KRW", "USD", "EUR", "JPY")], default="KRW")
    proposal = models.TextField(blank=True)
    processing_note = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_by_session = models.CharField(max_length=40, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0), name="quote_amount_nonnegative")]


class RentalStock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="rental_stocks")
    subject_row = models.OneToOneField(ManagedRow, null=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField()
    total = models.PositiveIntegerField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["subject_snapshot", "id"]


class Rental(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOANED = "loaned", "Loaned"
        RETURNED = "returned", "Returned"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock = models.ForeignKey(RentalStock, on_delete=models.CASCADE, related_name="rentals")
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    content = models.TextField(blank=True)
    processing_note = models.TextField(blank=True)
    created_by_session = models.CharField(max_length=40, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="rental_quantity_positive"),
            models.UniqueConstraint(fields=["stock", "created_by_session"],
                condition=models.Q(status__in=["pending", "approved", "loaned"]), name="one_active_rental_per_session_stock"),
        ]


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


class ReservationSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="reservation_slots")
    subject_row = models.ForeignKey(ManagedRow, null=True, on_delete=models.SET_NULL)
    subject_snapshot = models.TextField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField()
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(capacity__gte=1), name="reservation_slot_capacity_positive"),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="reservation_slot_time_order"),
        ]


class Reservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slot = models.ForeignKey(ReservationSlot, on_delete=models.CASCADE, related_name="reservations")
    created_by_session = models.CharField(max_length=40, db_index=True)
    cancelled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["slot", "created_by_session"],
            condition=models.Q(cancelled=False), name="one_active_reservation_per_session_slot")]


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
