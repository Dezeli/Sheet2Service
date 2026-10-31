"""Approval summary and the single approved understanding call for one upload."""
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .claude import InferenceError
from .reservation_understanding import UnderstandingError, summary_lines
from .reservation_understanding_request import (fingerprint, run_understanding, understanding_approval_summary,
                                                understanding_request_body)
from .views import SessionView, owned


class UnderstandingView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        try:
            body = understanding_request_body(upload.analysis, file_name=upload.original_name)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        payload = {"approval": understanding_approval_summary(body), "understanding": upload.understanding}
        if upload.understanding:
            payload["summary"] = summary_lines(upload.understanding, upload.analysis)
        return Response(payload)

    def post(self, request, pk):
        upload = owned(request, pk)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("approved") is not True:
            raise ValidationError({"detail": "Claude API 호출 전 명시적 승인이 필요합니다."})
        note = data.get("approval_note")
        if not isinstance(note, str) or not note.strip():
            raise ValidationError({"detail": "승인 기록 문구가 필요합니다."})
        try:
            body = understanding_request_body(upload.analysis, file_name=upload.original_name)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        if data.get("request_fingerprint") not in (None, fingerprint(body)):
            raise ValidationError({"detail": "전송 내용이 바뀌었습니다. 다시 확인하고 승인해 주세요."})
        try:
            call, understanding, notes = run_understanding(upload, approval_note=note, approved_at=timezone.now())
        except (InferenceError, UnderstandingError, ValueError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"model_call_id": str(call.id), "understanding": understanding, "notes": notes,
                         "summary": summary_lines(understanding, upload.analysis), "usage": call.usage})
