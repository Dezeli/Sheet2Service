"""Deterministic derivation of a service from an understanding; no Claude calls."""
import json
from pathlib import Path

from django.test import SimpleTestCase

from .analysis import analyze
from .sheet_understanding import apply_overrides, validate_understanding
from .understanding_derivation import derive_blueprint

EXAMPLE = Path(__file__).resolve().parents[1] / "claude_api_settings" / "sheet_understanding_response.example.json"
SHEETS = Path(__file__).resolve().parents[1] / "evaluation" / "sheets"


class DerivationTests(SimpleTestCase):
    def setUp(self):
        self.report = analyze((SHEETS / "민원접수대장.csv").read_bytes())
        self.understanding, _ = validate_understanding(json.loads(EXAMPLE.read_text(encoding="utf-8")), self.report)

    def test_roles_shape_the_catalog(self):
        derived = derive_blueprint(self.understanding, self.report)
        catalog = derived["blueprint"]["catalog"]
        self.assertEqual(catalog["titleColumn"], 1)  # identifier when there is no title column
        self.assertEqual(catalog["visibleColumns"][:4], [1, 7, 5, 8])  # identifier, status, category, owner
        self.assertEqual(catalog["filterColumns"], [7, 5, 12, 8])
        self.assertEqual([chart["groupColumn"] for chart in catalog["charts"]], [7, 5, 8, 12])
        self.assertEqual(catalog["sort"], {"column": 2, "direction": "desc"})
        self.assertEqual(derived["blueprint"]["title"], "주민 민원")

    def test_flows_become_row_workflows_bound_to_their_columns(self):
        derived = derive_blueprint(self.understanding, self.report)
        first, second = derived["rowWorkflows"]
        self.assertEqual((first["id"], first["basis"], first["statusColumn"], first["initialState"]), ("row_1", "status_column", 7, "접수"))
        self.assertEqual((first["ownerColumn"], first["closedColumn"], first["resultColumn"]), (8, 10, 11))
        self.assertEqual(first["transitions"][0], {"from": "접수", "to": "배정", "actor": "admin"})
        self.assertEqual((second["basis"], second["flagColumn"], second["doneValue"], second["companionColumns"]),
                         ("flag_and_dates", 12, "Y", [13, 14]))
        self.assertEqual(second["companionDates"], [13])
        self.assertEqual(second["after"], "row_1")
        self.assertEqual(derived["createForm"], {"actor": "user", "columns": [3, 4, 5, 6]})

    def test_flag_done_value_follows_the_done_state_when_states_use_sheet_values(self):
        understanding = json.loads(json.dumps(self.understanding))
        understanding["processes"][1]["states"] = [{"value": "N", "kind": "waiting"}, {"value": "Y", "kind": "done"}]
        flow = derive_blueprint(understanding, self.report)["rowWorkflows"][1]
        self.assertEqual(flow["doneValue"], "Y")  # N is the more frequent value, but not the done one

    def test_excluded_and_unconfirmed_low_confidence_flows_are_skipped(self):
        understanding = json.loads(json.dumps(self.understanding))
        understanding["processes"][0]["confidence"] = "low"
        effective = apply_overrides(understanding, {"processes": {"p2": {"excluded": True}}})
        derived = derive_blueprint(effective, self.report)
        self.assertEqual(derived["rowWorkflows"], [])
        self.assertEqual(len([note for note in derived["notes"] if "확신이 낮아" in note or "사용자가 제외" in note]), 2)
        confirmed = apply_overrides(understanding, {"processes": {"p1": {"confirmed": True}}})
        self.assertEqual([flow["id"] for flow in derive_blueprint(confirmed, self.report)["rowWorkflows"]], ["row_1", "row_2"])

    def test_milestone_flow_uses_its_date_columns_as_stages(self):
        report = analyze((SHEETS / "장비대여대장.csv").read_bytes())
        understanding, _ = validate_understanding({
            "version": 1, "kind": "register", "subject": "장비 대여", "purpose": "장비 대여 대장",
            "actors": [{"id": "a1", "label": "대여자", "kind": "requester"}, {"id": "a2", "label": "담당자", "kind": "handler"}],
            "columnRoles": ["identifier", "title", "reference_code", "actor_name", "category", "date_created", "date_updated",
                            "date_event", "date_due", "date_closed", "amount", "amount", "derived", "flag", "date_event",
                            "owner", "note"],
            "columnConfidence": ["high"] * 17, "columnEvidence": [""] * 17,
            "processes": [{"id": "p1", "title": "장비 대여", "basis": "milestone_dates", "columns": [6, 7, 8, 10],
                           "states": [{"value": "신청", "kind": "start"}, {"value": "반납", "kind": "done"}],
                           "transitions": ["신청>반납:a2"], "evidence": "", "confidence": "high", "after": ""}],
            "lifecycle": {"rowCreated": "", "rowUpdated": "", "rowClosed": ""}, "questions": []}, report)
        flow = derive_blueprint(understanding, report)["rowWorkflows"][0]
        self.assertEqual(flow["dateColumns"], [6, 7, 8, 10])
        self.assertEqual([state["value"] for state in flow["states"]], ["신청일", "승인일", "대여일", "반납일"])
        self.assertEqual(len(flow["transitions"]), 3)
        self.assertEqual(flow["dueColumn"], 9)
