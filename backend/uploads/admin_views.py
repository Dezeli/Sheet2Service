"""Service data and shared choice management APIs, scoped to the upload session."""
from collections import Counter
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .analysis import missing
from .managed import ensure_imported, next_row_number, value_hash
from .models import FieldChoice, ManagedRow, Upload
from .views import SessionView, owned


def _column(upload, value):
    if type(value) is not int or value < 1 or value > upload.analysis["column_count"]:
        raise ValidationError({"detail": "올바른 필드 번호를 선택해 주세요."})
    return value


def _values(upload, values, previous=None):
    width = upload.analysis["column_count"]
    if not isinstance(values, list) or len(values) != width:
        raise ValidationError({"detail": "모든 필드의 선택 값을 전달해 주세요."})
    cleaned = []
    for number, value in enumerate(values, start=1):
        if value is None or value == "":
            cleaned.append(None)
            continue
        if not isinstance(value, str) or len(value) > 100_000 or missing(value):
            raise ValidationError({"detail": f"{number}번 필드의 선택 값이 올바르지 않습니다."})
        choice = FieldChoice.objects.filter(upload=upload, column_number=number,
                                            value_hash=value_hash(value)).first()
        if choice is None or choice.value != value or (not choice.active and
            (previous is None or previous[number - 1] != value)):
            raise ValidationError({"detail": f"{number}번 필드는 등록된 활성 후보만 선택할 수 있습니다."})
        cleaned.append(value)
    return cleaned


def _row_payload(row):
    return {"id": str(row.id), "row_number": row.row_number, "values": row.values}


def _usage(upload, choice):
    return ManagedRow.objects.filter(upload=upload, **{f"values__{choice.column_number - 1}": choice.value})


def _disable_choice(upload, choice, replacement_id=None, expected_usage=None, replacement_value=None):
    rows = _usage(upload, choice)
    count = rows.count()
    if expected_usage is not None and (type(expected_usage) is not int or expected_usage != count):
        raise ValidationError({"detail": "사용 건수가 변경됐습니다. 다시 확인해 주세요."})
    if count:
        if not replacement_id or expected_usage is None:
            raise ValidationError({"detail": "사용 중인 데이터의 대체 선택지를 지정해 주세요.", "usage_count": count})
        try:
            replacement_id = UUID(str(replacement_id))
        except (ValueError, TypeError) as exc:
            raise ValidationError({"detail": "대체 선택지가 올바르지 않습니다."}) from exc
        replacement = FieldChoice.objects.filter(pk=replacement_id, upload=upload,
            column_number=choice.column_number, active=True).exclude(pk=choice.pk).first()
        if replacement is None:
            raise ValidationError({"detail": "같은 필드의 다른 활성 선택지를 지정해 주세요."})
        if replacement_value is not None and replacement.value != replacement_value:
            raise ValidationError({"detail": "대체 선택지가 변경됐습니다. 다시 확인해 주세요."})
        changed = []
        for row in rows.select_for_update().iterator(chunk_size=500):
            row.values[choice.column_number - 1] = replacement.value
            changed.append(row)
        ManagedRow.objects.bulk_update(changed, ["values"], batch_size=500)
    choice.active = False
    return count


class FieldLabelView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, column):
        upload = owned(request, pk)
        _column(upload, column)
        if not isinstance(request.data, dict) or set(request.data) != {"label"}:
            raise ValidationError({"detail": "변경할 필드명을 전달해 주세요."})
        label = request.data["label"]
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 120 or any(ord(char) < 32 for char in label):
            raise ValidationError({"detail": "필드명은 줄바꿈 없이 1~120자로 입력해 주세요."})
        with transaction.atomic():
            locked = Upload.objects.select_for_update().get(pk=upload.pk)
            labels = dict(locked.field_labels)
            if label.strip() == locked.analysis["columns"][column - 1]["label"]:
                labels.pop(str(column), None)
            else:
                labels[str(column)] = label.strip()
            locked.field_labels = labels
            locked.save(update_fields=["field_labels"])
        return Response({"column": column, "label": label.strip(), "field_labels": labels})


class ManagedRowsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        rows = upload.managed_rows.all()
        query = request.query_params.get("q", "").strip()
        if len(query) > 200:
            raise ValidationError({"detail": "검색어는 200자 이하로 입력해 주세요."})
        if query:
            conditions = Q()
            for index in range(upload.analysis["column_count"]):
                conditions |= Q(**{f"values__{index}__icontains": query})
            rows = rows.filter(conditions)
        filter_column = request.query_params.get("filter_column", "")
        filter_value = request.query_params.get("filter_value", "")
        if filter_column:
            try:
                number = _column(upload, int(filter_column))
            except (ValueError, TypeError) as exc:
                raise ValidationError({"detail": "필터 컬럼이 올바르지 않습니다."}) from exc
            if len(filter_value) > 100_000:
                raise ValidationError({"detail": "필터 값이 너무 깁니다."})
            if filter_value:
                rows = rows.filter(**{f"values__{number - 1}": filter_value})
        elif filter_value:
            raise ValidationError({"detail": "필터 컬럼을 선택해 주세요."})
        count = rows.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        start = (page - 1) * 20
        return Response({"page": page, "row_count": count,
                         "rows": [_row_payload(row) for row in rows.order_by("row_number")[start:start + 20]],
                         "has_next": page * 20 < count})

    def post(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "데이터 형식이 올바르지 않습니다."})
        with transaction.atomic():
            locked = type(upload).objects.select_for_update().get(pk=upload.pk)
            row = ManagedRow.objects.create(upload=locked, row_number=next_row_number(locked),
                                            values=_values(locked, request.data.get("values")))
        return Response(_row_payload(row), status=201)


class ManagedRowView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, row_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "데이터 형식이 올바르지 않습니다."})
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            row = get_object_or_404(ManagedRow.objects.select_for_update(), pk=row_id, upload=upload)
            row.values = _values(upload, request.data.get("values"), previous=row.values)
            row.save(update_fields=["values"])
        return Response(_row_payload(row))

    def delete(self, request, pk, row_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
            row.delete()
        return Response(status=204)


class FieldChoicesView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        try:
            number = int(request.query_params.get("column", ""))
        except ValueError as exc:
            raise ValidationError({"detail": "필드 번호가 필요합니다."}) from exc
        _column(upload, number)
        choices = FieldChoice.objects.filter(upload=upload, column_number=number)
        counts = Counter(ManagedRow.objects.filter(upload=upload).values_list(f"values__{number - 1}", flat=True).iterator(chunk_size=500))
        return Response({"column": number, "choices": [
            {"id": str(choice.id), "value": choice.value, "active": choice.active, "usage_count": counts[choice.value]}
            for choice in choices]})

    def post(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "데이터 형식이 올바르지 않습니다."})
        number = _column(upload, request.data.get("column"))
        value = request.data.get("value")
        if not isinstance(value, str) or not value.strip() or len(value) > 100_000:
            raise ValidationError({"detail": "후보 값을 입력해 주세요."})
        digest = value_hash(value)
        if FieldChoice.objects.filter(upload=upload, column_number=number, value_hash=digest).exists():
            raise ValidationError({"detail": "이미 등록된 후보입니다."})
        choice = FieldChoice.objects.create(upload=upload, column_number=number,
                                            value=value, value_hash=digest)
        return Response({"id": str(choice.id), "value": choice.value, "active": True}, status=201)


class FieldChoiceView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk, choice_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        choice = get_object_or_404(FieldChoice, pk=choice_id, upload=upload)
        return Response({"id": str(choice.id), "value": choice.value, "active": choice.active,
                         "usage_count": _usage(upload, choice).count()})

    def patch(self, request, pk, choice_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict) or not request.data or any(key not in ("value", "active", "replacement_id", "replacement_value", "expected_usage", "expected_value") for key in request.data):
            raise ValidationError({"detail": "후보 값 또는 사용 여부만 변경할 수 있습니다."})
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            choice = get_object_or_404(FieldChoice.objects.select_for_update(), pk=choice_id, upload=upload)
            if any(key in request.data for key in ("replacement_id", "replacement_value", "expected_usage", "expected_value")) and request.data.get("active") is not False:
                raise ValidationError({"detail": "대체 값은 사용 중지할 때만 지정할 수 있습니다."})
            if "value" in request.data and request.data.get("active") is False:
                raise ValidationError({"detail": "이름 변경과 사용 중지는 각각 처리해 주세요."})
            if "expected_value" in request.data and choice.value != request.data["expected_value"]:
                raise ValidationError({"detail": "선택지가 변경됐습니다. 다시 확인해 주세요."})
            if "value" in request.data:
                value = request.data["value"]
                if not isinstance(value, str) or not value.strip() or len(value) > 100_000:
                    raise ValidationError({"detail": "후보 값이 올바르지 않습니다."})
                digest = value_hash(value)
                if FieldChoice.objects.filter(upload=upload, column_number=choice.column_number,
                                              value_hash=digest).exclude(pk=choice.pk).exists():
                    raise ValidationError({"detail": "이미 등록된 후보입니다."})
                if value != choice.value:
                    rows = ManagedRow.objects.filter(upload=upload)
                    changed = []
                    index = choice.column_number - 1
                    for row in rows.iterator(chunk_size=500):
                        if row.values[index] == choice.value:
                            row.values[index] = value
                            changed.append(row)
                    ManagedRow.objects.bulk_update(changed, ["values"], batch_size=500)
                    choice.value = value
                    choice.value_hash = digest
            if "active" in request.data:
                if type(request.data["active"]) is not bool:
                    raise ValidationError({"detail": "사용 여부는 참 또는 거짓이어야 합니다."})
                if request.data["active"]:
                    choice.active = True
                else:
                    _disable_choice(upload, choice, request.data.get("replacement_id"), request.data.get("expected_usage"), request.data.get("replacement_value"))
            choice.save(update_fields=["value", "value_hash", "active"])
        return Response({"id": str(choice.id), "value": choice.value, "active": choice.active})

    def delete(self, request, pk, choice_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            choice = get_object_or_404(FieldChoice.objects.select_for_update(), pk=choice_id, upload=upload)
            _disable_choice(upload, choice)
            choice.save(update_fields=["active"])
        return Response(status=204)
