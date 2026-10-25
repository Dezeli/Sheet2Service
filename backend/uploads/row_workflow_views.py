"""Operate a register sheet through its row workflows; no model calls."""
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .managed import ensure_imported, next_row_number
from .models import ManagedRow, RowHistory, Upload
from .row_workflow import TransitionError, apply_transition, create_row_values, flow_payload, row_state
from .service_blueprint_views import apply_blueprint
from .sheet_understanding import apply_overrides
from .understanding_derivation import derive_blueprint
from .views import SessionView, owned


def row_payload(row, flows):
    return {"id": str(row.id), "row_number": row.row_number, "values": row.values,
            "flows": flow_payload(flows, row.values) if flows else {}, "mine": bool(row.created_by_session)}


def _flows(upload):
    if not upload.service_blueprint:
        raise Http404
    return upload.service_blueprint.get("rowWorkflows", [])


class UnderstandingApplyView(SessionView):
    """Make the service the effective understanding derives, with no provider call."""
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        if not upload.understanding:
            raise ValidationError({"detail": "먼저 시트를 이해해야 서비스를 만들 수 있습니다."})
        effective = apply_overrides(upload.understanding, upload.understanding_overrides or {})
        derived = derive_blueprint(effective, upload.analysis)
        blueprint = {**derived["blueprint"], "rowWorkflows": derived["rowWorkflows"]}
        if derived["createForm"]:
            blueprint["createForm"] = derived["createForm"]
        with transaction.atomic():
            locked = Upload.objects.select_for_update().get(pk=upload.pk)
            apply_blueprint(locked, blueprint)
        return Response({"blueprint": blueprint, "notes": derived["notes"]})


class RowTransitionView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk, row_id):
        upload = owned(request, pk)
        flows = _flows(upload)
        data = request.data if isinstance(request.data, dict) else {}
        flow = next((item for item in flows if item["id"] == data.get("flow_id")), None)
        if flow is None or data.get("actor") not in ("user", "admin") or not isinstance(data.get("to"), str):
            raise ValidationError({"detail": "상태 변경 형식이 올바르지 않습니다."})
        inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
        ensure_imported(upload)
        with transaction.atomic():
            row = get_object_or_404(ManagedRow.objects.select_for_update(), pk=row_id, upload=upload)
            if data["actor"] == "user" and row.created_by_session != (request.session.session_key or ""):
                raise ValidationError({"detail": "본인이 접수한 건만 변경할 수 있습니다."})
            before = row_state(flow, row.values)
            try:
                values, changes = apply_transition(flow, flows, row.values, to=data["to"], actor=data["actor"], inputs=inputs)
            except TransitionError as exc:
                raise ValidationError({"detail": str(exc)}) from exc
            row.values = values
            row.save(update_fields=["values"])
            RowHistory.objects.create(row=row, flow_id=flow["id"], from_state=before, to_state=data["to"], actor=data["actor"],
                                      session_key=request.session.session_key or "", changes=changes)
        return Response(row_payload(row, flows))


class RowHistoryView(SessionView):
    def get(self, request, pk, row_id):
        upload = owned(request, pk)
        flows = _flows(upload)
        row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
        titles = {flow["id"]: flow["title"] for flow in flows}
        return Response({"items": [{"flow": titles.get(item.flow_id, item.flow_id), "from": item.from_state, "to": item.to_state,
                                    "actor": item.actor, "changes": item.changes, "created_at": item.created_at.isoformat()}
                                   for item in row.history.all()]})


class RowCreateView(SessionView):
    """A requester adds a row through the derived form; flow columns start at their initial state."""
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        flows = _flows(upload)
        ensure_imported(upload)
        rows = ManagedRow.objects.filter(upload=upload, created_by_session=request.session.session_key or "").order_by("-row_number")[:50]
        return Response({"items": [row_payload(row, flows) for row in rows]})

    def post(self, request, pk):
        upload = owned(request, pk)
        flows = _flows(upload)
        form = upload.service_blueprint.get("createForm")
        if not form:
            raise ValidationError({"detail": "이 서비스에는 접수 폼이 없습니다."})
        inputs = request.data.get("values") if isinstance(request.data, dict) and isinstance(request.data.get("values"), dict) else None
        if inputs is None:
            raise ValidationError({"detail": "입력 값이 필요합니다."})
        ensure_imported(upload)
        if not request.session.session_key:
            request.session.create()
        with transaction.atomic():
            locked = Upload.objects.select_for_update().get(pk=upload.pk)
            try:
                values = create_row_values(form, locked.service_blueprint, locked.analysis["column_count"], inputs)
            except TransitionError as exc:
                raise ValidationError({"detail": str(exc)}) from exc
            row = ManagedRow.objects.create(upload=locked, row_number=next_row_number(locked), values=values,
                                            created_by_session=request.session.session_key)
            RowHistory.objects.create(row=row, flow_id="", from_state="", to_state="created", actor="user",
                                      session_key=request.session.session_key, changes={})
        return Response(row_payload(row, flows), status=201)
