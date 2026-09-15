"""Provider-compatible JSON schema; semantic constraints stay in the validator."""


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _array(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string"}
COLUMN_IDS = _array(TEXT)
CARDINALITIES = ("one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown")

# Lengths, uniqueness, ID patterns and cross-references are validated locally.
# Only the provider's supported structural constraints are sent to the API.
OUTPUT_SCHEMA = _object({
    "schema_version": {"type": "integer", "enum": [1]},
    "summary": TEXT,
    "entities": _array(_object({
        "id": TEXT,
        "name": TEXT,
        "column_ids": COLUMN_IDS,
        "rationale": TEXT,
    })),
    "relations": _array(_object({
        "from_entity": TEXT,
        "to_entity": TEXT,
        "cardinality": {"type": "string", "enum": list(CARDINALITIES)},
        "column_ids": COLUMN_IDS,
        "rationale": TEXT,
    })),
    "questions": _array(_object({
        "question": TEXT,
        "column_ids": COLUMN_IDS,
        "reason": TEXT,
    })),
})
