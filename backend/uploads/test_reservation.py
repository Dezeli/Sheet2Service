"""Offline API and PostgreSQL concurrency checks for generic reservations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from . import test_feature_selection as fixtures
from .models import Reservation, ReservationSlot


class ReservationFixture:
    mutate = fixtures.FeatureSelectionTests.mutate
    recorded = fixtures.FeatureSelectionTests.recorded

    def setUp(self):
        fixtures.FeatureSelectionTests.setUp(self)
        call = self.recorded({
            "user_flows": [fixtures.flow("reservation")],
            "admin_flows": [fixtures.flow("manage_reservations")],
        })
        response = self.mutate("workflow/", {"features": [{"model_call_id": str(call.id), "index": 0, "scope": "user"}]})
        self.assertEqual(response.status_code, 200)
        self.start = (timezone.now() + timedelta(days=2)).replace(microsecond=0)
        self.row = self.upload.managed_rows.first()

    def slot(self, row=None, offset=0, size=1):
        return self.mutate("reservation-slots/", {
            "row_id": str((row or self.row).pk),
            "starts_at": (self.start + timedelta(hours=offset)).isoformat(),
            "ends_at": (self.start + timedelta(hours=offset + 1)).isoformat(), "capacity": size,
        })

    def book(self, slot):
        return self.mutate("reservations/", {"slot_id": slot["id"]})


class ReservationApiTests(ReservationFixture, APITestCase):
    def test_reservation_composes_with_inquiry_catalog_and_application(self):
        call = self.recorded({
            "user_flows": [fixtures.flow("request_review"), fixtures.flow("reservation")],
            "admin_flows": [fixtures.flow("review_requests"), fixtures.flow("manage_reservations")],
        })
        refs = [{"scope": "user", "model_call_id": str(call.id), "index": index} for index in (0, 1)]
        response = self.mutate("workflow/", {"features": [*refs,
            fixtures.reference("inquiry"), fixtures.reference("catalog")]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["selected"]["modules"]), 4)
        self.assertEqual(self.book(self.slot().data).status_code, 201)

    def test_book_duplicate_cancel_and_rebook(self):
        slot = self.slot().data
        booking = self.book(slot)
        self.assertEqual(booking.status_code, 201)
        self.assertEqual(self.mutate(f"reservations/{booking.data['id']}/", {"cancelled": 1}, "patch").status_code, 400)
        self.assertEqual(self.book(slot).status_code, 400)
        self.assertEqual(self.client.get(self.base + "reservation-slots/").data["slots"][0]["remaining"], 0)
        self.assertEqual(self.mutate(f"reservations/{booking.data['id']}/", {"cancelled": True}, "patch").status_code, 200)
        self.assertEqual(self.book(slot).status_code, 201)
        self.assertEqual(self.client.get(self.base + "reservations/?mine=1").data["count"], 2)

    def test_capacity_and_foreign_bookings_not_shown_as_mine(self):
        slot = self.slot().data
        foreign = Reservation.objects.create(slot_id=slot["id"], created_by_session="another-user")
        self.assertEqual(self.book(slot).status_code, 400)
        self.assertEqual(self.client.get(self.base + "reservations/?mine=1").data["count"], 0)
        self.assertEqual(self.client.get(self.base + "reservations/").data["count"], 1)
        self.assertEqual(self.mutate(f"reservations/{foreign.pk}/", {"cancelled": True}, "patch").status_code, 404)
        self.assertEqual(APIClient().get(self.base + "reservations/").status_code, 404)

    def test_overlapping_slots_rejected_but_adjacent_and_other_items_allowed(self):
        self.assertEqual(self.slot().status_code, 201)
        self.assertEqual(self.slot(offset=0.5).status_code, 400)
        self.assertEqual(self.slot(offset=1).status_code, 201)
        other = self.upload.managed_rows.last()
        self.assertEqual(self.slot(row=other).status_code, 201)

    def test_user_cannot_book_overlapping_times_on_different_items(self):
        first = self.slot().data
        other = self.slot(row=self.upload.managed_rows.last()).data
        self.assertEqual(self.book(first).status_code, 201)
        self.assertEqual(self.book(other).status_code, 400)
        self.assertEqual(self.book(self.slot(offset=1).data).status_code, 201)

    def test_capacity_change_and_closed_slot_preserve_existing_reservations(self):
        slot = self.slot(size=2).data
        Reservation.objects.create(slot_id=slot["id"], created_by_session="another-user")
        self.assertEqual(self.book(slot).status_code, 201)
        path = f"reservation-slots/{slot['id']}/"
        self.assertEqual(self.mutate(path, {"capacity": 1}, "patch").status_code, 400)
        response = self.mutate(path, {"capacity": 3, "closed": True}, "patch")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["booked"], 2)
        self.assertEqual(self.client.get(self.base + "reservation-slots/?available=1").data["slots"], [])
        self.assertEqual(self.book(slot).status_code, 400)

    def test_past_and_deleted_subjects_cannot_be_booked(self):
        slot = self.slot().data
        ReservationSlot.objects.filter(pk=slot["id"]).update(starts_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.book(slot).status_code, 400)
        slot2 = self.slot(offset=3).data
        self.row.delete()
        self.assertEqual(self.book(slot2).status_code, 400)

    def test_started_reservation_cannot_be_cancelled(self):
        slot = self.slot().data
        booking = self.book(slot).data
        ReservationSlot.objects.filter(pk=slot["id"]).update(starts_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.mutate(f"reservations/{booking['id']}/", {"cancelled": True}, "patch").status_code, 400)

    def test_validation_foreign_rows_and_disabled_template(self):
        valid = {"row_id": str(self.row.pk), "starts_at": self.start.isoformat(),
                 "ends_at": (self.start + timedelta(hours=1)).isoformat(), "capacity": 1}
        for changes in [{"capacity": True}, {"capacity": 0}, {"row_id": "bad"},
                        {"starts_at": "2030-01-01T10:00:00"}, {"ends_at": valid["starts_at"]}]:
            self.assertEqual(self.mutate("reservation-slots/", {**valid, **changes}).status_code, 400)
        slot = self.slot().data
        self.assertEqual(self.mutate(f"reservation-slots/{slot['id']}/", {"closed": "yes"}, "patch").status_code, 400)
        self.assertEqual(self.client.get(self.base + "reservations/?page=bad").status_code, 400)
        self.assertEqual(self.mutate("workflow/", {"features": [fixtures.reference("inquiry")]}).status_code, 200)
        self.assertEqual(self.book(slot).status_code, 400)


class ReservationConcurrencyTests(ReservationFixture, TransactionTestCase):
    def test_simultaneous_submissions_create_one_active_booking(self):
        slot = self.slot().data
        barrier = Barrier(2)
        cookies = self.client.cookies.copy()

        def submit():
            close_old_connections()
            try:
                client = APIClient(enforce_csrf_checks=True)
                client.cookies = cookies.copy()
                barrier.wait(timeout=5)
                return client.post(self.base + "reservations/", {"slot_id": slot["id"]},
                    format="json", HTTP_X_CSRFTOKEN=self.token).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(results), [201, 400])
        self.assertEqual(Reservation.objects.filter(slot_id=slot["id"], cancelled=False).count(), 1)
