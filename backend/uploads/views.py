from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import MAX_BYTES, TableError, analyze
from .booking_rules import rules_of
from .claude import InferenceError
from .managed import ensure_imported, managed_chart_counts, managed_report, rows_page
from .models import Upload
from .reservation_service import build_service
from .reservation_understanding import UnderstandingError, summary_lines
from .reservation_understanding_request import (fingerprint, run_understanding, understanding_approval_summary,
                                                understanding_request_body)


class BrowserSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        self.enforce_csrf(request)
        return None


class SessionView(APIView):
    authentication_classes = [BrowserSessionAuthentication]
    permission_classes = [AllowAny]


def payload(upload):
    return {
        "id": str(upload.id), "name": upload.original_name, "size": upload.size,
        "file_type": upload.file_type, "encoding": upload.encoding,
        "field_labels": upload.field_labels,
        "analysis": managed_report(upload) if upload.managed else upload.analysis,
        "created_at": upload.created_at.isoformat(),
    }


def owned(request, pk):
    return get_object_or_404(Upload, pk=pk, session_key=request.session.session_key or "")


class BootstrapView(SessionView):
    def get(self, request):
        if not request.session.session_key:
            request.session.create()
        return Response({"csrf_token": get_token(request)})


class UploadView(SessionView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            raise ValidationError({"detail": "업로드할 파일을 선택해 주세요."})
        file_type = Path(file.name).suffix.lower().lstrip(".")
        if file_type != "csv":
            raise ValidationError({"detail": "CSV 파일을 선택해 주세요. Excel에서 CSV로 내보낼 수 있습니다."})
        if not 0 < file.size <= MAX_BYTES:
            raise ValidationError({"detail": "파일은 0바이트보다 크고 10MB 이하여야 합니다."})
        data = file.read()
        encoding = request.data.get("encoding", "auto")
        try:
            result = analyze(data, encoding, request.data.get("allow_replacement") == "true")
        except TableError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        if not request.session.session_key:
            request.session.create()
        upload = Upload(
            session_key=request.session.session_key, original_name=file.name,
            file_type=file_type, size=file.size,
            encoding=result["source"]["encoding"], analysis=result,
        )
        file.seek(0)
        upload.original.save(file.name, file, save=False)
        try:
            with transaction.atomic():
                upload.save()
                ensure_imported(upload)
        except Exception:
            upload.original.delete(save=False)
            raise
        return Response(payload(upload), status=201)


class DetailView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        return Response(payload(owned(request, pk)))

    def post(self, request, pk):
        upload = owned(request, pk)
        encoding = request.data.get("encoding", upload.encoding or "auto")
        if not isinstance(encoding, str):
            raise ValidationError({"detail": "인코딩은 문자열이어야 합니다."})
        with upload.original.open("rb") as original:
            data = original.read()
        try:
            result = analyze(data, encoding, request.data.get("allow_replacement") is True)
        except TableError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        upload.analysis = result
        upload.encoding = result["source"]["encoding"]
        upload.save(update_fields=["analysis", "encoding"])
        return Response(payload(upload))


def landing_persona(config):
    """Where a freshly generated service opens: the booker side when there is one."""
    ids = [persona["id"] for persona in config["personas"]]
    for wanted in ("booker", "viewer", "admin"):
        if wanted in ids:
            return wanted
    return ids[0] if ids else "admin"


def service_payload(upload):
    config = upload.service_config
    # services built before booking rules existed get them derived on the way out
    if "booking" in config:
        config = {**config, "booking": {**config["booking"], "rules": rules_of(config)}}
    understanding = upload.understanding or {}
    return {"upload": payload(upload), "service": config,
            "understanding": {"questions": understanding.get("questions", []),
                              "summary": summary_lines(understanding, upload.analysis) if understanding else []},
            "counts": {"resources": upload.resources.count(), "slots": upload.slots.count(),
                       "bookings": upload.bookings.count()},
            "landing": landing_persona(config)}


class ServiceView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_config:
            raise Http404
        ensure_imported(upload)
        return Response(service_payload(upload))


class OriginalView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        return FileResponse(upload.original.open("rb"), as_attachment=True, filename=upload.original_name)


class RowsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호는 양의 정수여야 합니다."}) from exc
        row_count = upload.managed_rows.count()
        page_size = 20
        if page < 1 or page > max(1, (row_count + page_size - 1) // page_size):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        rows = [{"row_number": row["row_number"], "values": row["values"]}
                for row in rows_page(upload, page, page_size)]
        return Response({"page": page, "page_size": page_size, "row_count": row_count,
                         "rows": rows, "has_next": page * page_size < row_count})


class ChartCountsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        raw = request.query_params.get("columns", "")
        parts = raw.split(",")
        if not 1 <= len(parts) <= 28 or any(not part.isdecimal() for part in parts):
            raise ValidationError({"detail": "집계할 컬럼 번호를 지정해 주세요."})
        numbers = list(dict.fromkeys(int(part) for part in parts))
        if any(number < 1 or number > upload.analysis["column_count"] for number in numbers):
            raise ValidationError({"detail": "컬럼 번호가 범위를 벗어났습니다."})
        summaries = managed_chart_counts(upload, numbers)
        return Response({"row_count": upload.managed_rows.count(), "columns": summaries})


class GenerateView(SessionView):
    """GET: what the single understanding call will send. POST: run it and build the service."""
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        try:
            body = understanding_request_body(upload.analysis, file_name=upload.original_name)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({**understanding_approval_summary(body), "requires_approval": True,
                         "already_generated": bool(upload.service_config)})

    def post(self, request, pk):
        upload = owned(request, pk)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("approved") is not True:
            raise ValidationError({"detail": "Claude API 호출 전 명시적 승인이 필요합니다."})
        approval_note = data.get("approval_note")
        if not isinstance(approval_note, str) or not approval_note.strip():
            raise ValidationError({"detail": "승인 기록 문구가 필요합니다."})
        try:
            body = understanding_request_body(upload.analysis, file_name=upload.original_name)
            if data.get("request_fingerprint") not in (None, fingerprint(body)):
                raise ValidationError({"detail": "전송 내용이 바뀌었습니다. 다시 확인하고 승인해 주세요."})
            call, understanding, notes = run_understanding(upload, approval_note=approval_note, approved_at=timezone.now())
            config, counts = build_service(upload, understanding)
        except (InferenceError, UnderstandingError, ValueError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"model_call_id": str(call.id), "status": call.status, "usage": call.usage,
                         "notes": notes, "counts": counts, **service_payload(upload)})
