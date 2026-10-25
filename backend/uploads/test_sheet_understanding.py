"""Operational signals and the SheetUnderstanding contract; no Claude calls."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from .analysis import analyze
from .models import ModelCall, Upload
from .sheet_understanding import validate_understanding
from .sheet_understanding_request import understanding_request_body

EXAMPLE = Path(__file__).resolve().parents[1] / "claude_api_settings" / "sheet_understanding_response.example.json"
SHEETS = Path(__file__).resolve().parents[1] / "evaluation" / "sheets"


def complaints_csv():
    return (SHEETS / "민원접수대장.csv").read_bytes()


class OperationalSignalTests(SimpleTestCase):
    def setUp(self):
        self.report = analyze(complaints_csv())
        self.signals = self.report["signals"]

    def test_small_value_sets_flags_and_identifiers_are_found(self):
        self.assertIn(7, [item["column"] for item in self.signals["value_sets"]])
        self.assertEqual([item["column"] for item in self.signals["flags"]], [12])
        self.assertEqual(self.signals["identifiers"][0]["column"], 1)
        self.assertIn({"column": 4, "kind": "phone", "share": 1.0}, self.signals["patterns"])

    def test_conditional_missing_shows_which_columns_follow_a_status(self):
        by_status = next(item for item in self.signals["conditional_missing"] if item["given"] == 7 and item["column"] == 10)
        self.assertGreater(by_status["missing_by_value"]["접수"], 0.9)
        self.assertLess(by_status["missing_by_value"]["완료"], 0.1)

    def test_fill_chain_and_clusters_group_the_reply_columns_after_closing(self):
        pairs = {(item["earlier"], item["later"]) for item in self.signals["fill_chain"]}
        self.assertIn((10, 13), pairs)  # 회신일 is only filled once 처리일 exists
        self.assertNotIn(1, {item["earlier"] for item in self.signals["fill_chain"]})  # always-filled columns imply nothing
        self.assertTrue(any({10, 13, 14} <= set(group) for group in self.signals["flow_clusters"]))

    def test_dates_order_and_gap_recover_the_seven_day_rule(self):
        gap = next(item for item in self.signals["date_gaps"] if (item["earlier"], item["later"]) == (2, 9))
        self.assertEqual((gap["days"], gap["share"]), (7, 1.0))
        self.assertIn((2, 10), {(item["earlier"], item["later"]) for item in self.signals["date_order"]})

    def test_numeric_relation_is_found_on_the_equipment_sheet(self):
        signals = analyze((SHEETS / "장비대여대장.csv").read_bytes())["signals"]
        self.assertIn({"left": 11, "op": "minus", "right": 12, "equals": 13, "ratio": 1.0}, signals["numeric_relations"])
        self.assertIn((7, 8), {(item["earlier"], item["later"]) for item in signals["fill_chain"]})  # 승인일 before 대여일

    def test_tiny_sheets_skip_signals(self):
        report = analyze("프로그램,분류\n도예,문화\n요가,건강\n".encode())
        self.assertNotIn("value_sets", report["signals"])


class UnderstandingContractTests(SimpleTestCase):
    def setUp(self):
        self.report = analyze(complaints_csv())
        self.example = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_passes_untouched(self):
        result, notes = validate_understanding(self.example, self.report)
        self.assertEqual(notes, [])
        self.assertEqual(result["kind"], "register")
        self.assertEqual([process["basis"] for process in result["processes"]], ["status_column", "flag_and_dates"])
        self.assertEqual(result["processes"][0]["transitions"][0], {"from": "접수", "to": "배정", "actor": "a1"})
        self.assertEqual(result["processes"][1]["after"], "p1")

    def test_invented_states_and_bad_references_are_lowered_not_rejected(self):
        broken = json.loads(json.dumps(self.example))
        broken["columnRoles"] = broken["columnRoles"][:5]
        broken["processes"][0]["states"].append({"value": "검토", "kind": "active"})
        broken["processes"][0]["transitions"].append("검토>완료:a9")
        broken["processes"][0]["columns"].append(99)
        broken["processes"][1]["after"] = "p2"
        broken["kind"] = "diary"
        result, notes = validate_understanding(broken, self.report)
        self.assertEqual(len(result["columnRoles"]), 14)
        self.assertEqual(result["columnRoles"][5:], ["unknown"] * 9)
        self.assertEqual([state["value"] for state in result["processes"][0]["states"]], ["접수", "배정", "처리중", "완료", "반려"])
        self.assertEqual(len(result["processes"][0]["transitions"]), 4)
        self.assertEqual(result["processes"][0]["columns"], [7, 8, 10, 11])
        self.assertEqual(result["processes"][1]["after"], "p1")  # self-reference dropped, then derived from the fill chain
        self.assertEqual(result["kind"], "mixed")
        self.assertEqual(len(notes), 6)

    def test_after_is_derived_from_the_fill_chain_when_the_model_leaves_it_empty(self):
        quiet = json.loads(json.dumps(self.example))
        quiet["processes"][1]["after"] = ""
        result, _ = validate_understanding(quiet, self.report)
        self.assertEqual(result["processes"][1]["after"], "p1")
        self.assertEqual(result["processes"][0]["after"], "")

    def test_one_state_flag_flow_gets_its_waiting_state_and_transition(self):
        ticked = json.loads(json.dumps(self.example))
        ticked["processes"][1]["states"] = [{"value": "Y", "kind": "done"}]
        ticked["processes"][1]["transitions"] = []
        result, notes = validate_understanding(ticked, self.report)
        flow = result["processes"][1]
        self.assertEqual([state["value"] for state in flow["states"]], ["N", "Y"])
        self.assertEqual(flow["transitions"], [{"from": "N", "to": "Y", "actor": ""}])
        self.assertTrue(any("대기 상태" in note for note in notes))

    def test_status_flow_without_observed_values_becomes_inferred(self):
        guessed = json.loads(json.dumps(self.example))
        guessed["processes"][0]["columns"] = [6]  # free text, no value set
        result, notes = validate_understanding(guessed, self.report)
        self.assertEqual(result["processes"][0]["basis"], "inferred")

    def test_request_body_carries_signals_and_schema(self):
        body = understanding_request_body(self.report, file_name="민원접수대장.csv")
        self.assertIn('"conditional_missing"', body["messages"][0]["content"])
        schema = body["output_config"]["format"]["schema"]
        self.assertEqual(schema["properties"]["columnRoles"]["items"]["enum"][0], "identifier")
        self.assertNotIn("{{", body["messages"][0]["content"])
        self.assertEqual(body["max_tokens"], 16000)  # thinking shares the budget with the JSON


class UnderstandingApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(MEDIA_ROOT=temporary.name, ANTHROPIC_API_KEY="synthetic-test-secret")
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile("민원접수대장.csv", complaints_csv())},
                                    format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(uploaded.status_code, 201, uploaded.data)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/understanding/"

    def _provider(self, text):
        return (200, {"request-id": "synthetic"}, json.dumps({
            "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 1, "output_tokens": 1}}))

    @patch("uploads.sheet_understanding_views._post_message")
    def test_one_approved_call_stores_the_understanding(self, post_message):
        post_message.return_value = self._provider(EXAMPLE.read_text(encoding="utf-8"))
        approval = self.client.get(self.base + "approval/").data
        self.assertEqual(approval["planned_call_count"], 1)
        refused = self.client.post(self.base, {"approved": True}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(refused.status_code, 400)
        created = self.client.post(self.base, {"approved": True, "request_fingerprint": approval["request_fingerprint"],
                                               "approval_note": "synthetic"}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(created.status_code, 200, created.data)
        self.assertEqual(created.data["understanding"]["subject"], "주민 민원")
        self.assertTrue(any("민원 처리" in line for line in created.data["summary"]))
        self.assertEqual(post_message.call_count, 1)
        self.assertEqual(ModelCall.objects.get().purpose, "시트 이해")
        again = self.client.post(self.base, {"approved": True, "request_fingerprint": approval["request_fingerprint"],
                                             "approval_note": "synthetic"}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertTrue(again.data["already_created"])
        self.assertEqual(post_message.call_count, 1)
        self.assertEqual(self.client.get(self.base).data["understanding"]["kind"], "register")

    @patch("uploads.sheet_understanding_views._post_message")
    def test_corrections_overlay_the_model_reading_without_a_call(self, post_message):
        post_message.return_value = self._provider(EXAMPLE.read_text(encoding="utf-8"))
        approval = self.client.get(self.base + "approval/").data
        self.client.post(self.base, {"approved": True, "request_fingerprint": approval["request_fingerprint"],
                                     "approval_note": "synthetic"}, format="json", HTTP_X_CSRFTOKEN=self.token)
        patched = self.client.patch(self.base, {"kind": "ledger", "columnRoles": {"13": "date_closed", "99": "note", "2": "bogus"},
                                                "processes": {"p2": {"excluded": True}, "p9": {"confirmed": True}},
                                                "answers": {"0": " 네, 접수일 기준 7일입니다. ", "5": "없는 질문"}},
                                    format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["overrides"], {"kind": "ledger", "columnRoles": {"13": "date_closed"},
                                                     "processes": {"p2": {"excluded": True}},
                                                     "answers": {"0": "네, 접수일 기준 7일입니다."}})
        effective = patched.data["understanding"]
        self.assertEqual((effective["kind"], effective["columnRoles"][12], effective["columnEvidence"][12]),
                         ("ledger", "date_closed", "사용자가 지정"))
        self.assertTrue(effective["processes"][1]["excluded"])
        self.assertEqual(effective["questions"][0]["answer"], "네, 접수일 기준 7일입니다.")
        self.assertEqual(patched.data["original"]["kind"], "register")  # the model's reading is kept apart
        again = self.client.patch(self.base, {"processes": {"p2": {"confirmed": True}}}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(again.data["overrides"]["processes"], {"p2": {"excluded": True, "confirmed": True}})
        cleared = self.client.patch(self.base, {"reset": True}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual((cleared.data["overrides"], cleared.data["understanding"]["kind"]), ({}, "register"))
        self.assertEqual(post_message.call_count, 1)

    @patch("uploads.sheet_understanding_views._post_message")
    def test_bad_response_is_recorded_and_changes_nothing(self, post_message):
        post_message.return_value = self._provider("not json")
        approval = self.client.get(self.base + "approval/").data
        failed = self.client.post(self.base, {"approved": True, "request_fingerprint": approval["request_fingerprint"],
                                              "approval_note": "synthetic"}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(failed.status_code, 400)
        self.upload.refresh_from_db()
        self.assertIsNone(self.upload.understanding)
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.FAILED)
