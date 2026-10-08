"""Import CSV once, then read and update service data in PostgreSQL."""

import csv
import hashlib
import io
from collections import Counter

from django.db import transaction
from django.db.models import Max

from .analysis import csv_text, missing
from .models import FieldChoice, ManagedRow, Upload


def value_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_imported(upload):
    if upload.managed:
        return
    with transaction.atomic():
        locked = Upload.objects.select_for_update().get(pk=upload.pk)
        if locked.managed:
            upload.managed = True
            return
        with locked.original.open("rb") as original:
            data = original.read()
        text, _, _ = csv_text(data, locked.encoding, allow_replacement=True)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        next(reader, None)
        width = locked.analysis["column_count"]
        rows = []
        choices = {}
        for row_number, row in enumerate(reader, start=2):
            if all(missing(value) for value in row):
                continue
            values = [row[index] if index < len(row) else None
                      for index in range(width)]
            rows.append(ManagedRow(upload=locked, row_number=row_number, values=values))
            for number, value in enumerate(values, start=1):
                if not missing(value):
                    choices[(number, value_hash(value))] = FieldChoice(
                        upload=locked, column_number=number, value=value, value_hash=value_hash(value))
        ManagedRow.objects.bulk_create(rows, batch_size=500)
        FieldChoice.objects.bulk_create(choices.values(), batch_size=500)
        locked.managed = True
        locked.save(update_fields=["managed"])
        upload.managed = True


def rows_page(upload, page, page_size=20):
    start = (page - 1) * page_size
    return [{"id": str(row.id), "row_number": row.row_number, "values": row.values}
            for row in ManagedRow.objects.filter(upload=upload).order_by("row_number")[start:start + page_size]]


def managed_report(upload):
    report = dict(upload.analysis)
    report["row_count"] = ManagedRow.objects.filter(upload=upload).count()
    report["preview"] = [{"row_number": row["row_number"], "values": row["values"]}
                         for row in rows_page(upload, 1)]
    return report


def next_row_number(upload):
    highest = ManagedRow.objects.filter(upload=upload).aggregate(number=Max("row_number"))["number"]
    return max(highest or 1, 1) + 1


def managed_chart_counts(upload, column_numbers):
    counts = {number: Counter() for number in column_numbers}
    total = 0
    for values in ManagedRow.objects.filter(upload=upload).values_list("values", flat=True).iterator(chunk_size=500):
        total += 1
        for number in column_numbers:
            value = values[number - 1]
            counts[number][None if missing(value) else value] += 1
    result = {}
    for number, categories in counts.items():
        sorted_groups = sorted(categories.items(), key=lambda item: item[1], reverse=True)
        if len(sorted_groups) > 8:
            visible = sorted_groups[:7]
            remainder = sorted_groups[7:]
            visible.append((f"나머지 {len(remainder)}개 분류", sum(count for _, count in remainder)))
        else:
            visible = sorted_groups
        result[f"column_{number}"] = {
            "total": total,
            "groups": [{"label": "값 없음" if label is None else label, "count": count,
                        "ratio": count / total if total else 0} for label, count in visible],
        }
    return result
