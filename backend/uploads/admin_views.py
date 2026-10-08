"""Service data and shared choice management APIs, scoped to the upload session."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .analysis import missing
from .managed import ensure_imported, next_row_number, rows_page, value_hash
from .models import FieldChoice, ManagedRow
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


class ManagedRowsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        count = upload.managed_rows.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        return Response({"page": page, "row_count": count, "rows": rows_page(upload, page),
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
            row = get_object_or_404(ManagedRow.objects.select_for_update(), pk=row_id, upload=upload)
            row.values = _values(upload, request.data.get("values"), previous=row.values)
            row.save(update_fields=["values"])
        return Response(_row_payload(row))

    def delete(self, request, pk, row_id):
        upload = owned(request, pk)
        ensure_imported(upload)
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
        return Response({"column": number, "choices": [
            {"id": str(choice.id), "value": choice.value, "active": choice.active}
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

    def patch(self, request, pk, choice_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict) or not request.data or any(key not in ("value", "active") for key in request.data):
            raise ValidationError({"detail": "후보 값 또는 사용 여부만 변경할 수 있습니다."})
        with transaction.atomic():
            choice = get_object_or_404(FieldChoice.objects.select_for_update(), pk=choice_id, upload=upload)
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
                choice.active = request.data["active"]
            choice.save(update_fields=["value", "value_hash", "active"])
        return Response({"id": str(choice.id), "value": choice.value, "active": choice.active})

    def delete(self, request, pk, choice_id):
        upload = owned(request, pk)
        ensure_imported(upload)
        choice = get_object_or_404(FieldChoice, pk=choice_id, upload=upload)
        choice.active = False
        choice.save(update_fields=["active"])
        return Response(status=204)
