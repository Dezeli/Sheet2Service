"""Serve the derived service: catalog rows with their row-workflow states."""
from django.db.models import Q
from django.http import Http404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .managed import ensure_imported
from .models import ManagedRow
from .row_workflow import flow_payload
from .service_blueprint import catalog_labels, catalog_sort
from .views import SessionView, owned


def apply_blueprint(upload, blueprint):
    """Activate a validated config and mirror its display names into the admin-editable labels."""
    upload.service_blueprint = blueprint
    labels = catalog_labels(blueprint)
    if labels:
        upload.field_labels = {**(upload.field_labels or {}), **labels}
    upload.save(update_fields=["service_blueprint", "field_labels"])


class BlueprintRowsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_blueprint:
            raise Http404
        ensure_imported(upload)
        catalog = upload.service_blueprint["catalog"]
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        query = request.query_params.get("q", "").strip()
        if len(query) > 200:
            raise ValidationError({"detail": "검색어는 200자 이하여야 합니다."})
        rows = ManagedRow.objects.filter(upload=upload)
        if query:
            if not catalog["searchColumns"]:
                raise ValidationError({"detail": "이 서비스에는 검색이 설정되지 않았습니다."})
            conditions = Q()
            for number in catalog["searchColumns"]:
                conditions |= Q(**{f"values__{number - 1}__icontains": query})
            rows = rows.filter(conditions)
        raw_column = request.query_params.get("filter_column", "")
        filter_value = request.query_params.get("filter_value", "")
        if raw_column:
            try:
                number = int(raw_column)
            except ValueError as exc:
                raise ValidationError({"detail": "필터 컬럼이 올바르지 않습니다."}) from exc
            if number not in catalog["filterColumns"] or len(filter_value) > 1000:
                raise ValidationError({"detail": "허용되지 않은 필터입니다."})
            if filter_value:
                rows = rows.filter(**{f"values__{number - 1}": filter_value})
        elif filter_value:
            raise ValidationError({"detail": "필터 컬럼을 선택해 주세요."})
        count = rows.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        sort = catalog_sort(catalog)
        if sort is None:
            rows = rows.order_by("row_number")
        else:
            # Values are JSON strings, so this is text order (ISO dates sort correctly).
            key = f"values__{sort[0] - 1}"
            rows = rows.order_by(f"-{key}" if sort[1] == "desc" else key, "row_number")
        items = rows[(page - 1) * 20:page * 20]
        flows = upload.service_blueprint.get("rowWorkflows", [])
        session = request.session.session_key or ""
        return Response({"page": page, "row_count": count,
                         "rows": [{"id": str(row.id), "row_number": row.row_number, "values": row.values,
                                   "flows": flow_payload(flows, row.values) if flows else {},
                                   "mine": bool(row.created_by_session) and row.created_by_session == session}
                                  for row in items]})
