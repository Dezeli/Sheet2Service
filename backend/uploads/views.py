from pathlib import Path

from django.utils import timezone
from django.http import FileResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .analysis import MAX_BYTES, TableError, analyze, chart_counts, read_page
from .claude import approval_summary, run_inference
from .inference import InferenceError
from .preview_request_v2 import PreviewRequestError
from .models import Upload


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
        "file_type": upload.file_type, "encoding": upload.encoding, "analysis": upload.analysis,
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
            upload.save()
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


class OriginalView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        return FileResponse(upload.original.open("rb"), as_attachment=True, filename=upload.original_name)


class RowsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호는 양의 정수여야 합니다."}) from exc
        row_count = upload.analysis["row_count"]
        page_size = 20
        if page < 1 or page > max(1, (row_count + page_size - 1) // page_size):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        with upload.original.open("rb") as original:
            data = original.read()
        try:
            rows = read_page(data, encoding=upload.encoding,
                             width=upload.analysis["column_count"], page=page, page_size=page_size)
        except (TableError, ValueError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"page": page, "page_size": page_size, "row_count": row_count,
                         "rows": rows, "has_next": page * page_size < row_count})


class ChartCountsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        raw = request.query_params.get("columns", "")
        parts = raw.split(",")
        if not 1 <= len(parts) <= 28 or any(not part.isdecimal() for part in parts):
            raise ValidationError({"detail": "집계할 컬럼 번호를 지정해 주세요."})
        numbers = list(dict.fromkeys(int(part) for part in parts))
        if any(number < 1 or number > upload.analysis["column_count"] for number in numbers):
            raise ValidationError({"detail": "컬럼 번호가 범위를 벗어났습니다."})
        with upload.original.open("rb") as original:
            data = original.read()
        try:
            summaries = chart_counts(data, encoding=upload.encoding, column_numbers=numbers)
        except (TableError, ValueError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"row_count": upload.analysis["row_count"], "columns": summaries})


class InferenceView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        try:
            return Response(approval_summary(owned(request, pk)))
        except PreviewRequestError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def post(self, request, pk):
        upload = owned(request, pk)
        if request.data.get("approved") is not True:
            raise ValidationError({"detail": "Claude API 호출 전 명시적 승인이 필요합니다."})
        approval_note = request.data.get("approval_note")
        if not isinstance(approval_note, str) or not approval_note.strip():
            raise ValidationError({"detail": "승인 기록 문구가 필요합니다."})
        try:
            call, result = run_inference(upload, approval_note=approval_note, approved_at=timezone.now())
        except (InferenceError, PreviewRequestError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({
            "model_call_id": str(call.id),
            "status": call.status,
            "result": result,
            "usage": call.usage,
        })
