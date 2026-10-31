"""ReservationUnderstanding contract and the single approved call; no network."""
import json
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from .analysis import analyze
from .models import ModelCall, Upload
from .reservation_understanding import (FEATURES, PERSONAS, ROLES, SHEET_KINDS, UnderstandingError,
                                        parse_understanding_response, summary_lines, understanding_schema,
                                        validate_understanding)
from .reservation_understanding_request import understanding_approval_summary, understanding_request_body

BOOKINGS = ("예약번호,기관명,상품명,숙박일자,예약자,인원,상태,승인일,결제여부,비고\n" + "".join(
    f"R{index:04d},{org},{room},2026-03-{day:02d},{name},{size},{status},{approved},{paid},\n"
    for index, (org, room, day, name, size, status, approved, paid) in enumerate([
        ("변산 자연휴양림", "우럭", 3, "김**", 4, "체크아웃", "2026-02-20", "Y"),
        ("변산 자연휴양림", "바다향기5", 16, "이**", 2, "예약완료", "2026-03-01", "Y"),
        ("유명산 자연휴양림", "크낙새", 5, "박**", 5, "예약완료", "2026-02-28", "Y"),
        ("유명산 자연휴양림", "크낙새", 9, "최**", 3, "취소", "", "N"),
        ("변산 자연휴양림", "우럭", 11, "정**", 4, "승인대기", "", "N"),
        ("유명산 자연휴양림", "소나무", 12, "강**", 2, "예약완료", "2026-03-02", "Y"),
        ("변산 자연휴양림", "바다향기5", 20, "조**", 6, "체크아웃", "2026-03-05", "Y"),
        ("유명산 자연휴양림", "소나무", 21, "윤**", 2, "취소", "", "N"),
        ("변산 자연휴양림", "우럭", 22, "장**", 4, "승인대기", "", "N"),
        ("유명산 자연휴양림", "크낙새", 25, "임**", 5, "예약완료", "2026-03-10", "Y"),
    ], 1))).encode("utf-8")


def model_answer(**overrides):
    answer = {
        "version": 1, "sheetKind": "booking_records", "subject": "국립자연휴양림 객실",
        "summary": "휴양림 객실 예약 기록이다.\n객실 예약 서비스로 만든다.\n이용객이 예약하고 관리자가 승인한다.",
        "columnRoles": ["identifier", "resource_group", "resource", "date", "booker", "party_size", "status",
                        "updated_at", "payment", "note"],
        "columnEvidence": [""] * 10,
        "resourceColumns": [2, 3],
        "booking": {"mode": "approval", "statusColumn": 7,
                    "stateValues": ["승인대기", "예약완료", "체크아웃", "취소", "노쇼"],
                    "stateKinds": ["requested", "approved", "completed", "cancelled", "other"],
                    "evidence": "승인대기와 예약완료가 함께 있고 승인일이 예약완료에서만 채워진다."},
        "personas": [
            {"id": "booker", "title": "휴양림 이용객", "scopeColumn": 0,
             "features": ["browse_resources", "make_reservation", "inquiry"], "evidence": ""},
            {"id": "admin", "title": "휴양림 관리자", "scopeColumn": 0,
             "features": ["review_reservations", "manage_resources", "manage_schedule", "reply_inquiries"], "evidence": ""},
            {"id": "org_manager", "title": "기관 담당자", "scopeColumn": 2, "features": ["review_reservations"],
             "evidence": "기관명이 둘 이상이다."},
            {"id": "staff", "title": "담당자", "scopeColumn": 0, "features": ["review_reservations"], "evidence": ""},
        ],
        "questions": ["승인대기 상태를 관리자가 직접 승인하는지 확인이 필요하다."],
    }
    answer.update(overrides)
    return answer


class ContractTests(SimpleTestCase):
    def setUp(self):
        self.report = analyze(BOOKINGS)

    def test_signals_see_the_status_values_and_the_payment_flag(self):
        signals = self.report["signals"]
        statuses = next(item for item in signals["value_sets"] if item["column"] == 7)
        self.assertEqual({entry["value"] for entry in statuses["values"]}, {"체크아웃", "예약완료", "취소", "승인대기"})
        self.assertEqual([item["column"] for item in signals["flags"]], [9])

    def test_schema_uses_fixed_vocabularies_and_parallel_arrays(self):
        schema = understanding_schema(self.report)
        self.assertEqual(schema["properties"]["sheetKind"]["enum"], list(SHEET_KINDS))
        self.assertEqual(schema["properties"]["columnRoles"]["items"]["enum"], list(ROLES))
        self.assertEqual(schema["properties"]["personas"]["items"]["properties"]["id"]["enum"], list(PERSONAS))
        self.assertEqual(schema["properties"]["personas"]["items"]["properties"]["features"]["items"]["enum"], list(FEATURES))
        self.assertEqual(schema["properties"]["booking"]["properties"]["stateKinds"]["items"]["type"], "string")

    def test_good_answer_passes_with_only_required_features_added(self):
        understanding, notes = validate_understanding(model_answer(), self.report)
        self.assertEqual(understanding["resourceColumns"], [2, 3])
        self.assertEqual(understanding["booking"]["mode"], "approval")
        self.assertEqual([state["value"] for state in understanding["booking"]["states"]],
                         ["승인대기", "예약완료", "체크아웃", "취소"])  # 노쇼 is not in the data
        booker = next(persona for persona in understanding["personas"] if persona["id"] == "booker")
        self.assertEqual(booker["features"], ["browse_resources", "make_reservation", "inquiry", "my_reservations"])
        admin = next(persona for persona in understanding["personas"] if persona["id"] == "admin")
        self.assertIn("manage_data", admin["features"])
        self.assertEqual([persona["id"] for persona in understanding["personas"]], ["booker", "admin", "org_manager"])
        self.assertTrue(any("노쇼" not in note and "상태 값 1개" in note for note in notes))
        self.assertTrue(any("staff" in note for note in notes))
        self.assertIn("예약 대상 컬럼: 기관명 > 상품명", summary_lines(understanding, self.report))

    def test_missing_pieces_are_filled_from_the_data_instead_of_rejected(self):
        answer = model_answer(resourceColumns=[], personas=[], questions=[])
        answer["booking"] = {"mode": "weird", "statusColumn": 7, "stateValues": ["예약완료"], "stateKinds": ["approved"],
                             "evidence": ""}
        answer["columnRoles"][1] = "wide_resource"
        understanding, notes = validate_understanding(answer, self.report)
        self.assertEqual(understanding["columnRoles"][1], "other")
        self.assertEqual(understanding["resourceColumns"], [3])  # from the remaining resource role
        self.assertEqual(understanding["booking"]["mode"], "approval")
        self.assertEqual({state["value"] for state in understanding["booking"]["states"]},
                         {"예약완료", "승인대기", "체크아웃", "취소"})
        self.assertEqual([persona["id"] for persona in understanding["personas"]], ["booker", "admin"])
        self.assertEqual(understanding["personas"][0]["features"], ["browse_resources", "make_reservation", "my_reservations"])
        self.assertTrue(any("booker 페르소나" in note for note in notes))

    def test_aggregate_sheets_get_no_booking_flow_and_a_viewer(self):
        answer = model_answer(sheetKind="aggregate", resourceColumns=[])
        answer["booking"]["mode"] = "approval"
        understanding, _ = validate_understanding(answer, self.report)
        self.assertEqual(understanding["booking"]["mode"], "none")
        ids = [persona["id"] for persona in understanding["personas"]]
        self.assertNotIn("booker", ids)
        self.assertIn("viewer", ids)
        admin = next(persona for persona in understanding["personas"] if persona["id"] == "admin")
        self.assertNotIn("review_reservations", admin["features"])
        self.assertIn("manage_data", admin["features"])

    def test_bad_json_and_non_objects_are_rejected(self):
        for raw in ("not json", json.dumps([1, 2]), '{"a": 1, "a": 2}'):
            with self.assertRaises(UnderstandingError):
                parse_understanding_response(raw, self.report)

    def test_request_body_carries_file_name_signals_and_schema(self):
        body = understanding_request_body(self.report, file_name="휴양림 예약.csv")
        content = body["messages"][0]["content"]
        self.assertIn('"휴양림 예약.csv"', content)
        self.assertIn('"value_sets"', content)
        self.assertEqual(body["output_config"]["format"]["schema"]["properties"]["version"]["enum"], [1])
        self.assertGreaterEqual(body["max_tokens"], 16000)
        self.assertIn("예약", body["system"])
        summary = understanding_approval_summary(body)
        self.assertEqual(summary["planned_call_count"], 1)
        self.assertEqual(len(summary["request_fingerprint"]), 64)


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class UnderstandingApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile("휴양림 예약.csv", BOOKINGS)},
                                    format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.url = f"/api/uploads/{self.upload.pk}/understanding/"

    def post(self, body):
        return self.client.post(self.url, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    @patch("uploads.claude._post_message")
    def test_one_approved_call_stores_the_understanding(self, post_message):
        preview = self.client.get(self.url)
        self.assertEqual(preview.data["approval"]["planned_call_count"], 1)
        self.assertIsNone(preview.data["understanding"])
        post_message.assert_not_called()
        self.assertEqual(self.post({"approved": False, "approval_note": "no"}).status_code, 400)
        post_message.assert_not_called()
        provider = {"content": [{"type": "text", "text": json.dumps(model_answer(), ensure_ascii=False)}],
                    "usage": {"input_tokens": 10, "output_tokens": 20}, "stop_reason": "end_turn"}
        post_message.return_value = (200, {"request-id": "req_test"}, json.dumps(provider))
        response = self.post({"approved": True, "approval_note": "one call approved",
                              "request_fingerprint": preview.data["approval"]["request_fingerprint"]})
        self.assertEqual(response.status_code, 200)
        post_message.assert_called_once()
        self.assertEqual(response.data["understanding"]["subject"], "국립자연휴양림 객실")
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.understanding["booking"]["statusColumn"], 7)
        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.SUCCEEDED)
        self.assertEqual(call.parsed_result["understanding"]["sheetKind"], "booking_records")
        self.assertTrue(self.client.get(self.url).data["summary"])
        self.assertEqual(APIClient().get(self.url).status_code, 404)

    @patch("uploads.claude._post_message")
    def test_bad_response_is_recorded_and_changes_nothing(self, post_message):
        provider = {"content": [{"type": "text", "text": "not json"}], "usage": {}, "stop_reason": "end_turn"}
        post_message.return_value = (200, {}, json.dumps(provider))
        self.assertEqual(self.post({"approved": True, "approval_note": "approved"}).status_code, 400)
        call = ModelCall.objects.get()
        self.assertEqual(call.status, ModelCall.Status.FAILED)
        self.assertEqual(call.response_body, json.dumps(provider))
        self.upload.refresh_from_db()
        self.assertIsNone(self.upload.understanding)
        provider["stop_reason"] = "max_tokens"
        provider["content"][0]["text"] = json.dumps(model_answer())
        post_message.return_value = (200, {}, json.dumps(provider))
        self.assertIn("길이 제한", self.post({"approved": True, "approval_note": "approved"}).data["detail"])


class PairingTests(SimpleTestCase):
    def test_notices_and_inquiries_are_paired_between_readers_and_writers(self):
        report = analyze(BOOKINGS)
        answer = model_answer()
        answer["personas"][0]["features"] = ["browse_resources", "notices"]          # booker reads notices
        answer["personas"][1]["features"] = ["review_reservations", "reply_inquiries"]  # admin answers inquiries
        understanding, notes = validate_understanding(answer, report)
        booker = next(p for p in understanding["personas"] if p["id"] == "booker")
        admin = next(p for p in understanding["personas"] if p["id"] == "admin")
        self.assertIn("manage_notices", admin["features"])
        self.assertIn("inquiry", booker["features"])
        self.assertTrue(any("manage_notices" in note for note in notes))
