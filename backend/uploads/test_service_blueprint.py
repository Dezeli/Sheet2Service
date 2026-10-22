"""Offline contract checks for generated and revised service proposals."""

import copy
import json
from pathlib import Path
from unittest import TestCase

from .analysis import analyze
from .service_blueprint import BlueprintError, parse_blueprint_response, parse_revision_response
from .service_blueprint_request import blueprint_schema


EXAMPLES = Path(__file__).resolve().parents[1] / "claude_api_settings"


class ServiceBlueprintTests(TestCase):
    def setUp(self):
        self.report = analyze("프로그램,분류,장소\n도예,문화,1층\n요가,건강,2층\n".encode())
        self.current = json.loads((EXAMPLES / "service_blueprint_response.example.json").read_text(encoding="utf-8"))

    def test_example_and_revision_are_valid_for_non_sports_csv(self):
        self.assertEqual(parse_blueprint_response(json.dumps(self.current), self.report), self.current)
        revised = json.loads((EXAMPLES / "service_blueprint_revision_response.example.json").read_text(encoding="utf-8"))
        self.assertEqual(parse_revision_response(json.dumps(revised), self.report, self.current), revised)

    def test_rejects_nonexistent_csv_column_and_invalid_state_transition(self):
        invalid = copy.deepcopy(self.current)
        invalid["catalog"]["titleColumn"] = 4
        with self.assertRaises(BlueprintError):
            parse_blueprint_response(json.dumps(invalid), self.report)
        invalid = copy.deepcopy(self.current)
        invalid["workflows"][0]["transitions"][0]["from"] = "missing"
        with self.assertRaises(BlueprintError):
            parse_blueprint_response(json.dumps(invalid), self.report)

    def test_unapplied_revision_cannot_mutate_existing_service(self):
        result = {"status": "unsupported", "message": "재고 관리 규칙은 아직 지원하지 않습니다.",
                  "blueprint": copy.deepcopy(self.current)}
        self.assertEqual(parse_revision_response(json.dumps(result), self.report, self.current), result)
        result["blueprint"]["catalog"]["filterColumns"] = []
        with self.assertRaises(BlueprintError):
            parse_revision_response(json.dumps(result), self.report, self.current)

    def test_rejects_extra_execution_fields_and_duplicate_json_keys(self):
        invalid = copy.deepcopy(self.current)
        invalid["workflows"][0]["code"] = "run()"
        with self.assertRaises(BlueprintError):
            parse_blueprint_response(json.dumps(invalid), self.report)
        with self.assertRaises(BlueprintError):
            parse_blueprint_response('{"version":1,"version":1}', self.report)

    def test_enum_schema_and_bounded_display_lists(self):
        report = analyze((",".join(f"column_{i}" for i in range(1, 17)) + "\n" +
                          ",".join(f"value_{i}" for i in range(1, 17)) + "\n").encode())
        schema = blueprint_schema(report)
        workflow = schema["properties"]["workflows"]["items"]
        self.assertEqual(workflow["properties"]["id"]["enum"], ["flow_1", "flow_2", "flow_3"])
        self.assertEqual(schema["properties"]["catalog"]["properties"]["titleColumn"]["enum"],
                         list(range(1, 17)))
        proposal = copy.deepcopy(self.current)
        proposal["catalog"]["visibleColumns"] = list(range(1, 15))
        proposal["catalog"]["filterColumns"] = list(range(1, 7))
        proposal["catalog"]["searchColumns"] = [1, 2, 2, 3]
        normalized = parse_blueprint_response(json.dumps(proposal), report)
        self.assertEqual(normalized["catalog"]["visibleColumns"], list(range(1, 13)))
        self.assertEqual(normalized["catalog"]["filterColumns"], [1, 2, 3, 4, 5])
        self.assertEqual(normalized["catalog"]["searchColumns"], [1, 2, 3])
        proposal["catalog"]["visibleColumns"].append(99)
        with self.assertRaises(BlueprintError):
            parse_blueprint_response(json.dumps(proposal), report)
