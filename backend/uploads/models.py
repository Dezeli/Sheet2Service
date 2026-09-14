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
