"""Provider-compatible JSON schema; semantic constraints stay in validators."""


def _object(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties if required is None else required),
        "additionalProperties": False,
    }


def _array(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string"}
COLUMN_IDS = _array(TEXT)
TEMPLATE_IDS = ("cards", "detail", "table", "grouped")
CHART_TYPES = ("bar", "donut")
CHART_AGGREGATES = ("count",)

# Lengths, uniqueness, ID patterns and cross-references are validated locally.
# Only provider-friendly structural constraints are sent to the API.
CHART_SCHEMA = _object({
    "type": {"type": "string", "enum": list(CHART_TYPES)},
    "title": TEXT,
    "groupBy": TEXT,
    "aggregate": {"type": "string", "enum": list(CHART_AGGREGATES)},
})

BINDINGS_SCHEMA = _object({
    "title": TEXT,
    "subtitle": TEXT,
    "image": TEXT,
    "badge": TEXT,
    "fields": COLUMN_IDS,
    "link": TEXT,
    "phone": TEXT,
    "group": TEXT,
}, required=())

PAGE_SCHEMA = _object({
    "id": TEXT,
    "template": {"type": "string", "enum": list(TEMPLATE_IDS)},
    "title": TEXT,
    "bindings": BINDINGS_SCHEMA,
    "detailPage": TEXT,
    "charts": _array(CHART_SCHEMA),
}, required=("id", "template", "title", "bindings"))

PREVIEW_SCHEMA = _object({
    "version": {"type": "integer", "enum": [1]},
    "title": TEXT,
    "pages": _array(PAGE_SCHEMA),
})

OUTPUT_SCHEMA = _object({
    "schema_version": {"type": "integer", "enum": [1]},
    "summary": TEXT,
    "preview": PREVIEW_SCHEMA,
    "questions": _array(_object({
        "question": TEXT,
        "column_ids": COLUMN_IDS,
        "reason": TEXT,
    })),
})
