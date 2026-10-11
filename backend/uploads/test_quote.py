"""Offline quote visibility, exact amounts, state transitions and isolation."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase

from . import test_feature_selection as fixtures
from .models import ModelCall, QuoteRequest


class QuoteFixture:
    mutate = fixtures.FeatureSelectionTests.mutate
    recorded = fixtures.FeatureSelectionTests.recorded

    def setUp(self):
        fixtures.FeatureSelectionTests.setUp(self)
        call = self.recorded({"user_flows": [fixtures.flow("quote")],
                              "admin_flows": [fixtures.flow("manage_quotes")]})
        self.reference = {"scope": "user", "model_call_id": str(call.pk), "index": 0}
        self.assertEqual(self.mutate("workflow/", {"features": [self.reference]}).status_code, 200)
        self.row = self.upload.managed_rows.first()
        response = self.mutate("quote-requests/", {"row_id": str(self.row.pk), "content": "설치 조건을 포함해 견적을 요청합니다."})
        self.assertEqual(response.status_code, 201)
        self.quote_id = response.data["id"]

    def process(self, action, **values):
        return self.mutate(f"quote-requests/{self.quote_id}/", {"action": action, **values}, "patch")

    def proposal(self, action="send", **changes):
        return self.process(action, **{"amount": "100.10", "currency": "USD", "proposal": "설치 포함 제안", **changes})


class QuoteApiTests(QuoteFixture, APITestCase):
    def test_draft_hidden_then_sent_offer_acceptance_and_completion(self):
        draft = self.proposal("save")
        self.assertEqual(draft.status_code, 200)
        self.assertEqual(draft.data["amount"], "100.10")
        self.assertEqual(draft.data["status"], "pending")
        user = self.client.get(self.base + "quote-requests/").data["quotes"][0]
        self.assertIsNone(user["amount"])
        self.assertEqual(user["proposal"], "")
        self.assertEqual(self.client.get(self.base + "quote-requests/?admin=1").data["quotes"][0]["amount"], "100.10")
        sent = self.process("send")
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.data["status"], "quoted")
        self.assertIsNotNone(sent.data["sent_at"])
        user = self.client.get(self.base + "quote-requests/").data["quotes"][0]
        self.assertEqual(user["amount"], "100.10")
        self.assertEqual(user["proposal"], "설치 포함 제안")
        self.assertEqual(self.process("accept").status_code, 200)
        self.assertEqual(self.process("start", processing_note="작업 시작").status_code, 200)
        self.assertEqual(self.process("complete", processing_note="작업 완료").status_code, 200)
        stored = QuoteRequest.objects.get(pk=self.quote_id)
        self.assertEqual(stored.amount, Decimal("100.10"))
        self.assertEqual(stored.status, "completed")
        self.assertEqual(ModelCall.objects.count(), 1)

    def test_offer_immutable_after_sending_and_state_order_enforced(self):
        for action in ("accept", "decline", "start", "complete"):
            self.assertEqual(self.process(action).status_code, 400)
        self.assertEqual(self.process("send").status_code, 400)
        self.assertEqual(self.proposal().status_code, 200)
        for action in ("send", "save"):
            self.assertEqual(self.proposal(action, amount="200.00").status_code, 400)
        self.assertEqual(self.process("start").status_code, 400)
        self.assertEqual(self.process("accept").status_code, 200)
        self.assertEqual(self.process("accept").status_code, 400)
        self.assertEqual(self.process("decline").status_code, 400)
        self.assertEqual(self.process("start").status_code, 200)
        self.assertEqual(self.process("cancel").status_code, 400)
        self.assertEqual(QuoteRequest.objects.get(pk=self.quote_id).amount, Decimal("100.10"))

    def test_user_decline_and_admin_request_rejection(self):
        self.proposal()
        self.assertEqual(self.process("decline").status_code, 200)
        self.assertEqual(self.process("accept").status_code, 400)
        another = self.mutate("quote-requests/", {"row_id": str(self.row.pk), "content": "별도 조건"})
        rejected = self.mutate(f"quote-requests/{another.data['id']}/", {"action": "reject", "processing_note": "지원 불가"}, "patch")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], "unavailable")
        self.assertEqual(rejected.data["processing_note"], "지원 불가")

    def test_cancellation_before_start_preserves_sent_offer(self):
        self.proposal()
        self.process("accept")
        cancelled = self.process("cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["amount"], "100.10")
        self.assertEqual(self.process("start").status_code, 400)

    def test_exact_amount_and_payload_validation(self):
        for amount in (100.10, True, None, "-1", "NaN", "Infinity", "1e3", "1.001", "1000000000000", "1,000", "01"):
            self.assertEqual(self.proposal("save", amount=amount).status_code, 400)
        for changes in ({"currency": "BAD"}, {"currency": []}, {"proposal": " "}, {"proposal": "x" * 5001}):
            self.assertEqual(self.proposal("save", **changes).status_code, 400)
        self.assertEqual(self.process("save", amount="1").status_code, 400)
        self.assertEqual(self.process("send", amount="1").status_code, 400)
        self.assertEqual(self.process("unknown").status_code, 400)
        self.assertEqual(self.process("accept", amount="1").status_code, 400)
        self.assertEqual(self.proposal("save", amount="0").status_code, 200)
        self.assertEqual(self.proposal("save", amount="999999999999.99").status_code, 200)

    def test_request_validation_isolation_and_csrf(self):
        for data in ({"row_id": "bad", "content": "조건"}, {"row_id": str(self.row.pk), "content": " "},
                     {"row_id": str(self.row.pk), "content": "x" * 5001},
                     {"row_id": str(self.row.pk), "content": "조건", "amount": "1"}):
            self.assertEqual(self.mutate("quote-requests/", data).status_code, 400)
        other = QuoteRequest.objects.create(upload=self.upload, subject_snapshot="다른 요청", content="조건", created_by_session="another-user")
        self.assertEqual(self.client.get(self.base + "quote-requests/").data["count"], 1)
        self.assertEqual(self.client.get(self.base + "quote-requests/?admin=1").data["count"], 2)
        self.assertEqual(self.mutate(f"quote-requests/{other.pk}/", {"action": "cancel"}, "patch").status_code, 404)
        anonymous = APIClient(enforce_csrf_checks=True)
        self.assertEqual(anonymous.get(self.base + "quote-requests/").status_code, 404)
        self.assertEqual(anonymous.patch(self.base + f"quote-requests/{self.quote_id}/", {"action": "send"}, format="json").status_code, 403)

    def test_pagination_deleted_item_and_feature_restore(self):
        QuoteRequest.objects.bulk_create([QuoteRequest(upload=self.upload, subject_snapshot=f"항목 {index}",
            content="조건", created_by_session=self.upload.session_key) for index in range(20)])
        self.assertTrue(self.client.get(self.base + "quote-requests/").data["has_next"])
        self.assertEqual(len(self.client.get(self.base + "quote-requests/?page=2").data["quotes"]), 1)
        self.assertEqual(self.client.get(self.base + "quote-requests/?page=bad").status_code, 400)
        self.row.delete()
        self.assertEqual(self.proposal().status_code, 200)
        self.mutate("workflow/", {"features": [fixtures.reference("inquiry")]})
        self.assertEqual(self.client.get(self.base + "quote-requests/").status_code, 400)
        self.mutate("workflow/", {"features": [fixtures.reference("inquiry"), fixtures.reference("catalog"), self.reference]})
        self.assertEqual(self.process("accept").status_code, 200)
        self.assertEqual(QuoteRequest.objects.count(), 21)


class QuoteConcurrencyTests(QuoteFixture, TransactionTestCase):
    def test_simultaneous_accept_decline_only_one_transition_succeeds(self):
        self.proposal()
        barrier = Barrier(2)
        cookies = self.client.cookies.copy()

        def respond(action):
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                client.cookies = cookies.copy()
                barrier.wait(timeout=5)
                return client.patch(self.base + f"quote-requests/{self.quote_id}/", {"action": action},
                    format="json", HTTP_X_CSRFTOKEN=self.token).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(respond, action) for action in ("accept", "decline")]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(results), [200, 400])
