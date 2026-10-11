"""Offline rental lifecycle, stock accounting and concurrent approval checks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase

from . import test_feature_selection as fixtures
from .models import ModelCall, Rental, RentalStock


class RentalFixture:
    mutate = fixtures.FeatureSelectionTests.mutate
    recorded = fixtures.FeatureSelectionTests.recorded

    def setUp(self):
        fixtures.FeatureSelectionTests.setUp(self)
        call = self.recorded({"user_flows": [fixtures.flow("rental")],
                              "admin_flows": [fixtures.flow("manage_rentals")]})
        self.reference = {"scope": "user", "model_call_id": str(call.pk), "index": 0}
        self.assertEqual(self.mutate("workflow/", {"features": [self.reference]}).status_code, 200)
        response = self.mutate("rental-stocks/", {"row_id": str(self.upload.managed_rows.first().pk), "total": 3})
        self.assertEqual(response.status_code, 201)
        self.stock = RentalStock.objects.get(pk=response.data["id"])

    def apply(self, quantity=2):
        return self.mutate("rentals/", {"stock_id": str(self.stock.pk), "quantity": quantity, "content": "대여 요청"})

    def process(self, item_id, status, **changes):
        return self.mutate(f"rentals/{item_id}/", {"status": status, **changes}, "patch")

    def available(self):
        return self.client.get(self.base + "rental-stocks/").data["stocks"][0]["available"]


class RentalApiTests(RentalFixture, APITestCase):
    def test_approval_handover_return_account_for_stock_exactly_once(self):
        request = self.apply()
        self.assertEqual(request.status_code, 201)
        self.assertEqual(self.available(), 3)
        self.assertEqual(self.apply().status_code, 400)
        item_id = request.data["id"]
        approved = self.process(item_id, "approved", processing_note="수령 가능")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["processing_note"], "수령 가능")
        self.assertEqual(self.available(), 1)
        self.assertEqual(self.process(item_id, "approved").status_code, 400)
        self.assertEqual(self.process(item_id, "loaned").status_code, 200)
        self.assertEqual(self.available(), 1)
        self.assertEqual(self.process(item_id, "cancelled").status_code, 400)
        self.assertEqual(self.process(item_id, "returned").status_code, 200)
        self.assertEqual(self.available(), 3)
        self.assertEqual(self.process(item_id, "returned").status_code, 400)
        self.assertEqual(self.apply().status_code, 201)
        self.assertEqual(ModelCall.objects.count(), 1)

    def test_pending_and_approved_cancellation_release_only_held_stock(self):
        pending = self.apply().data
        self.assertEqual(self.process(pending["id"], "cancelled").status_code, 200)
        self.assertEqual(self.available(), 3)
        approved = self.apply().data
        self.process(approved["id"], "approved")
        self.assertEqual(self.available(), 1)
        self.assertEqual(self.process(approved["id"], "cancelled").status_code, 200)
        self.assertEqual(self.available(), 3)

    def test_competing_pending_requests_cannot_be_approved_past_stock(self):
        first = self.apply().data
        second = Rental.objects.create(stock=self.stock, quantity=2, created_by_session="another-user")
        self.assertEqual(self.process(first["id"], "approved").status_code, 200)
        self.assertEqual(self.process(second.pk, "approved").status_code, 400)
        second.refresh_from_db()
        self.assertEqual(second.status, "pending")
        self.assertEqual(self.process(second.pk, "rejected").status_code, 200)
        self.assertEqual(self.available(), 1)

    def test_stock_changes_intake_and_deleted_row(self):
        request = self.apply().data
        self.process(request["id"], "approved")
        path = f"rental-stocks/{self.stock.pk}/"
        self.assertEqual(self.mutate(path, {"total": 1}, "patch").status_code, 400)
        self.assertEqual(self.mutate(path, {"total": 5, "active": False}, "patch").status_code, 200)
        self.assertEqual(self.client.get(self.base + "rental-stocks/?available=1").data["stocks"], [])
        self.assertEqual(self.available(), 3)
        self.assertEqual(self.process(request["id"], "loaned").status_code, 200)
        self.stock.subject_row.delete()
        self.assertEqual(self.process(request["id"], "returned").status_code, 200)
        self.assertEqual(self.available(), 5)
        self.assertEqual(self.apply().status_code, 400)
        self.assertEqual(self.client.get(self.base + "rentals/?mine=1").data["rentals"][0]["subject"], self.stock.subject_snapshot)

    def test_rejection_preserves_stock_and_illegal_transitions_fail(self):
        request = self.apply().data
        for status in ("loaned", "returned", "pending"):
            self.assertEqual(self.process(request["id"], status).status_code, 400)
        self.assertEqual(self.process(request["id"], "rejected").status_code, 200)
        self.assertEqual(self.available(), 3)
        self.assertEqual(self.process(request["id"], "approved").status_code, 400)

    def test_disabled_or_deleted_stock_cannot_be_approved(self):
        request = self.apply().data
        self.mutate(f"rental-stocks/{self.stock.pk}/", {"active": False}, "patch")
        self.assertEqual(self.process(request["id"], "approved").status_code, 400)
        self.mutate(f"rental-stocks/{self.stock.pk}/", {"active": True}, "patch")
        self.stock.subject_row.delete()
        self.assertEqual(self.process(request["id"], "approved").status_code, 400)
        self.assertEqual(self.process(request["id"], "rejected").status_code, 200)

    def test_isolation_validation_and_pagination(self):
        foreign = Rental.objects.create(stock=self.stock, quantity=1, created_by_session="another-user")
        self.assertEqual(self.client.get(self.base + "rentals/?mine=1").data["count"], 0)
        self.assertEqual(self.process(foreign.pk, "cancelled").status_code, 400)
        self.assertEqual(APIClient().get(self.base + "rentals/").status_code, 404)
        for quantity in (True, 0, -1, 1.5, "1", 4):
            self.assertEqual(self.apply(quantity).status_code, 400)
        self.assertEqual(self.mutate("rentals/", {"stock_id": "bad", "quantity": 1}).status_code, 400)
        self.assertEqual(self.mutate(f"rental-stocks/{self.stock.pk}/", {"active": "yes"}, "patch").status_code, 400)
        self.assertEqual(self.mutate("rental-stocks/", {"row_id": str(self.stock.subject_row_id), "total": 1}).status_code, 400)
        self.assertEqual(self.process(foreign.pk, "approved", processing_note="x" * 2001).status_code, 400)
        Rental.objects.bulk_create([Rental(stock=self.stock, quantity=1, created_by_session=f"old-{index}",
            status="returned") for index in range(20)])
        first = self.client.get(self.base + "rentals/").data
        self.assertEqual(first["count"], 21)
        self.assertTrue(first["has_next"])
        self.assertEqual(len(self.client.get(self.base + "rentals/?page=2").data["rentals"]), 1)
        self.assertEqual(self.client.get(self.base + "rentals/?page=bad").status_code, 400)

    def test_zero_stock_and_cancel_cannot_modify_admin_note(self):
        self.mutate(f"rental-stocks/{self.stock.pk}/", {"total": 0}, "patch")
        self.assertEqual(self.apply(1).status_code, 400)
        self.mutate(f"rental-stocks/{self.stock.pk}/", {"total": 3}, "patch")
        request = self.apply().data
        self.assertEqual(self.process(request["id"], "cancelled", processing_note="changed").status_code, 400)

    def test_selection_composition_and_restore(self):
        request = self.apply().data
        self.mutate("workflow/", {"features": [fixtures.reference("inquiry")]})
        self.assertEqual(self.client.get(self.base + "rentals/").status_code, 400)
        self.assertEqual(Rental.objects.count(), 1)
        selected = self.mutate("workflow/", {"features": [fixtures.reference("inquiry"),
            fixtures.reference("catalog"), self.reference]})
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.data["selected"]["modules"][-1]["admin"]["template"], "manage_rentals")
        self.assertEqual(self.process(request["id"], "approved").status_code, 200)


class RentalConcurrencyTests(RentalFixture, TransactionTestCase):
    def test_competing_approvals_only_hold_available_stock(self):
        RentalStock.objects.filter(pk=self.stock.pk).update(total=1)
        rentals = [Rental.objects.create(stock=self.stock, quantity=1, created_by_session=f"user-{index}") for index in range(2)]
        barrier = Barrier(2)
        cookies = self.client.cookies.copy()

        def approve(item):
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                client.cookies = cookies.copy()
                barrier.wait(timeout=5)
                return client.patch(self.base + f"rentals/{item.pk}/", {"status": "approved"},
                    format="json", HTTP_X_CSRFTOKEN=self.token).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(approve, item) for item in rentals]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(results), [200, 400])
        self.assertEqual(Rental.objects.filter(stock=self.stock, status="approved").count(), 1)
