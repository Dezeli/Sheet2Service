"""Ask once what a sheet is and how it is operated; store the validated answer on the upload."""
import json

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .analysis import TableError, analyze
from .call_records import finish_call, record_failure, start_call
from .claude import _extract_text, _post_message
from .inference import InferenceError
from .models import ModelCall
from .sheet_understanding import (UnderstandingError, apply_overrides, parse_understanding_response, summary_lines,
                                  validate_overrides)
from .sheet_understanding_request import (PURPOSE, fingerprint, understanding_approval_summary,
                                          understanding_request_body)
from .understanding_derivation import derive_blueprint
from .views import SessionView, owned


def ensure_signals(upload):
    """Uploads analyzed before operational signals existed get them from the stored original."""
    if isinstance(upload.analysis, dict) and "signals" in upload.analysis:
        return upload.analysis
    with upload.original.open("rb") as original:
        data = original.read()
    try:
        report = analyze(data, upload.encoding or "auto", allow_replacement=True)
    except TableError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    upload.analysis = {**upload.analysis, "signals": report["signals"]}
    upload.save(update_fields=["analysis"])
    return upload.analysis


def _approved(request, body):
    if not isinstance(request.data, dict) or request.data.get("approved") is not True \
            or request.data.get("request_fingerprint") != fingerprint(body) \
            or not isinstance(request.data.get("approval_note"), str) \
            or not request.data["approval_note"].strip():
        raise ValidationError({"detail": "전송 내용과 Claude 1회 호출 안내를 확인한 뒤 다시 요청해 주세요."})


def _payload(upload, notes=()):
    report = upload.analysis
    effective = apply_overrides(upload.understanding, upload.understanding_overrides or {})
    return {"understanding": effective, "original": upload.understanding,
            "overrides": upload.understanding_overrides or {},
            "summary": summary_lines(effective, report) if effective else [],
            # What the service would look like, recomputed from the effective understanding on every read.
            "derived": derive_blueprint(effective, report) if effective else None,
            "notes": list(notes)}


class UnderstandingApprovalView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        try:
            return Response(understanding_approval_summary(understanding_request_body(
                ensure_signals(upload), file_name=upload.original_name)))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class UnderstandingView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        latest = ModelCall.objects.filter(upload=upload, purpose=PURPOSE, status=ModelCall.Status.SUCCEEDED) \
            .order_by("-started_at").first()
        notes = (latest.parsed_result or {}).get("notes", []) if latest else []
        return Response(_payload(upload, notes))

    def patch(self, request, pk):
        """Store the user's corrections; no model call. An empty body clears them."""
        upload = owned(request, pk)
        if not upload.understanding:
            raise ValidationError({"detail": "먼저 시트를 이해해야 수정할 수 있습니다."})
        try:
            overrides = validate_overrides(request.data, upload.analysis, upload.understanding)
        except UnderstandingError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        merged = {**(upload.understanding_overrides or {})}
        for key, value in overrides.items():
            if key == "processes":  # per-flow flags accumulate (exclude now, confirm later)
                merged[key] = {flow: {**merged.get(key, {}).get(flow, {}), **flags} for flow, flags in
                               {**merged.get(key, {}), **value}.items()}
            else:
                merged[key] = {**merged.get(key, {}), **value} if isinstance(value, dict) else value
        if request.data.get("reset") is True:
            merged = {}
        upload.understanding_overrides = merged
        upload.save(update_fields=["understanding_overrides"])
        return Response(_payload(upload))

    def post(self, request, pk):
        """Exactly one provider request; a bad response leaves the stored understanding untouched."""
        upload = owned(request, pk)
        if upload.understanding and request.data.get("regenerate") is not True:
            return Response({**_payload(upload), "already_created": True})
        try:
            body = understanding_request_body(ensure_signals(upload), file_name=upload.original_name)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        _approved(request, body)
        call = start_call(upload=upload, purpose=PURPOSE, request_body=body,
                          approval_note=request.data["approval_note"], approved_at=timezone.now())
        response_text, http_status, headers, usage = "", None, {}, {}
        try:
            http_status, headers, response_text = _post_message(body)
            provider = json.loads(response_text)
            if not isinstance(provider, dict):
                raise UnderstandingError("Claude 응답 형식이 올바르지 않습니다.")
            usage = provider.get("usage", {})
            if not 200 <= http_status < 300:
                raise InferenceError("Claude API 요청이 실패했습니다.")
            if provider.get("stop_reason") == "max_tokens":
                raise UnderstandingError("Claude 응답이 길이 제한으로 중단되었습니다.")
            understanding, notes = parse_understanding_response(_extract_text(provider), upload.analysis)
            finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text,
                        http_status=http_status, provider_request_id=headers.get("request-id", ""),
                        parsed_result={"understanding": understanding, "notes": notes}, usage=usage)
        except Exception as exc:  # noqa: BLE001 - record first, then surface.
            record_failure(call, exc, response_body=response_text, http_status=http_status,
                           provider_request_id=headers.get("request-id", ""), usage=usage)
            if isinstance(exc, (ValueError, InferenceError)):
                raise ValidationError({"detail": str(exc)}) from exc
            raise
        upload.understanding = understanding
        upload.save(update_fields=["understanding"])
        return Response({**_payload(upload, notes), "already_created": False, "model_call_id": str(call.id)})
