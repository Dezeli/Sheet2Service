"""Resources, slots and bookings through the API, as each persona. No model call."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import Booking, Resource, Slot
from .test_fixtures import ServiceClientMixin
from .test_reservation_service import CATALOG, SLOTS, catalog_answer, slots_answer
from .test_reservation_understanding import BOOKINGS, model_answer


def future(days):
    return (timezone.localdate() + timedelta(days=days)).isoformat()


class BookingRecordsApiTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_resources_browse_by_level_and_search(self):
        top = self.client.get(self.base + "resources/").data
        self.assertEqual(top["levels"], ["기관명", "상품명"])
        self.assertEqual(sorted(item["name"] for item in top["resources"]), ["변산 자연휴양림", "유명산 자연휴양림"])
        self.assertEqual(top["resources"][0]["children_count"], 2)
        top["resources"].sort(key=lambda item: item["name"])
        rooms = self.client.get(self.base + f"resources/?parent={top['resources'][0]['id']}").data["resources"]
        self.assertEqual(sorted(item["name"] for item in rooms), ["바다향기5", "우럭"])
        rooms.sort(key=lambda item: item["name"])
        self.assertEqual(rooms[1]["booking_count"], 2)  # 승인대기 2건만 활성, 체크아웃은 끝난 예약
        found = self.client.get(self.base + "resources/?q=크낙").data["resources"]
        self.assertEqual([item["path"] for item in found], ["유명산 자연휴양림 / 크낙새"])
        detail = self.client.get(self.base + f"resources/{rooms[1]['id']}/").data
        self.assertEqual(detail["ancestors"][0]["name"], "변산 자연휴양림")

    def test_booker_reserves_a_room_for_a_date_then_admin_reviews(self):
        room = Resource.objects.get(upload=self.upload, path="변산 자연휴양림 / 우럭")
        org = room.parent
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(org.id), "date": future(3),
                                                   "booker": "홍길동"}).status_code, 400)  # must pick the leaf
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id),
                                                   "booker": "홍길동"}).status_code, 400)  # date model needs a date
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id), "date": future(3)}).status_code, 400)
        self.assertEqual(self.config["booking"]["unit"], "stay")  # 숙박일자 + 객실
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id), "date": future(3),
                                                   "end_date": future(3), "booker": "홍길동"}).status_code, 400)  # a stay needs a night
        created = self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id), "date": future(3), "end_date": future(5),
                                            "booker": "홍길동", "party_size": 3, "purpose": "가족 여행"})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], "requested")  # approval mode
        self.assertTrue(created.data["mine"])
        self.assertEqual(created.data["events"][0]["to"], "requested")
        # the same room on the same day is taken (capacity defaults to one)
        second = self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id), "date": future(4), "end_date": future(6), "booker": "김철수"})
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(room.id), "date": future(5), "end_date": future(7),
                                                   "booker": "박영희"}).status_code, 201)  # checkout day is free again
        self.assertEqual(second.status_code, 400)
        self.assertIn("가득", second.data["detail"])
        mine = self.client.get(self.base + "bookings/?persona=booker").data
        self.assertEqual(mine["count"], 2)
        booking_id = created.data["id"]
        self.assertEqual(self.mutate(f"bookings/{booking_id}/", {"persona": "booker", "action": "approve"}, "patch").status_code, 400)
        rejected = self.mutate(f"bookings/{booking_id}/", {"persona": "admin", "action": "reject"}, "patch")
        self.assertEqual(rejected.status_code, 400)  # a reason is required
        approved = self.mutate(f"bookings/{booking_id}/", {"persona": "admin", "action": "approve", "note": "확인"}, "patch")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual([event["to"] for event in approved.data["events"]], ["requested", "approved"])
        self.assertEqual(self.mutate(f"bookings/{booking_id}/", {"persona": "admin", "action": "approve"}, "patch").status_code, 400)
        cancelled = self.mutate(f"bookings/{booking_id}/", {"persona": "booker", "action": "cancel"}, "patch")
        self.assertEqual(cancelled.data["status"], "cancelled")
        other = APIClient(enforce_csrf_checks=True)
        self.assertEqual(other.get(self.base + "bookings/?persona=booker").status_code, 404)
        self.assertEqual(self.client.post(self.base + "bookings/", {"persona": "booker"}, format="json").status_code, 403)

    def test_admin_list_filters_stats_and_imported_records(self):
        everything = self.client.get(self.base + "bookings/?persona=admin").data
        self.assertEqual(everything["count"], 10)
        self.assertTrue(all(item["imported"] for item in everything["bookings"]))
        waiting = self.client.get(self.base + "bookings/?persona=admin&status=requested").data
        self.assertEqual(waiting["count"], 2)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=admin&q=크낙새").data["count"], 3)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=admin&status=bogus").status_code, 400)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=nobody").status_code, 400)
        approved = self.mutate(f"bookings/{waiting['bookings'][0]['id']}/", {"persona": "admin", "action": "approve"}, "patch")
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(approved.data["status_label"], "")
        stats = self.client.get(self.base + "bookings/stats/?persona=admin").data
        self.assertEqual((stats["total"], stats["counts"]["requested"], stats["counts"]["approved"], stats["imported"]), (10, 1, 5, 10))
        self.assertEqual(stats["top_resources"][0]["count"], 3)

    def test_org_manager_sees_only_its_organization(self):
        scopes = self.client.get(self.base + "bookings/scopes/?persona=org_manager").data
        self.assertEqual((scopes["label"], scopes["values"]), ("기관명", ["변산 자연휴양림", "유명산 자연휴양림"]))
        self.assertEqual(self.client.get(self.base + "bookings/?persona=org_manager").status_code, 400)
        scoped = self.client.get(self.base + "bookings/?persona=org_manager&scope=변산 자연휴양림").data
        self.assertEqual(scoped["count"], 5)
        self.assertTrue(all(item["resource"]["path"].startswith("변산") for item in scoped["bookings"]))
        self.assertEqual(self.client.get(self.base + "bookings/stats/?persona=org_manager&scope=변산 자연휴양림").data["total"], 5)
        booking = scoped["bookings"][0]["id"]
        self.assertEqual(self.mutate(f"bookings/{booking}/", {"persona": "org_manager", "action": "complete"}, "patch").status_code,
                         200 if scoped["bookings"][0]["status"] in ("approved", "in_use") else 400)

    def test_resource_management_create_rename_and_deactivate(self):
        top = self.client.get(self.base + "resources/").data["resources"]
        busan = next(item for item in top if item["name"] == "변산 자연휴양림")
        self.assertEqual(self.mutate("resources/", {"persona": "booker", "name": "새 객실"}).status_code, 400)
        created = self.mutate("resources/", {"persona": "admin", "name": "새 객실", "parent_id": busan["id"], "capacity": 2,
                                             "attributes": {"요금": "80000"}})
        self.assertEqual(created.status_code, 201)
        self.assertEqual((created.data["level"], created.data["path"]), (1, "변산 자연휴양림 / 새 객실"))
        self.assertEqual(self.mutate("resources/", {"persona": "admin", "name": "새 객실", "parent_id": busan["id"]}).status_code, 400)
        renamed = self.mutate(f"resources/{busan['id']}/", {"persona": "admin", "name": "변산"}, "patch")
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(Resource.objects.get(pk=created.data["id"]).path, "변산 / 새 객실")
        self.assertEqual(Booking.objects.filter(upload=self.upload, resource__path="변산 / 우럭").count(), 3)
        removed = self.mutate(f"resources/{created.data['id']}/", {"persona": "admin"}, "delete")
        self.assertEqual(removed.data, {"deleted": True, "deactivated": False})
        kept = self.mutate(f"resources/{busan['id']}/", {"persona": "admin"}, "delete")
        self.assertTrue(kept.data["deactivated"])
        self.assertEqual(self.client.get(self.base + "resources/").data["count"], 1)
        self.assertEqual(self.client.get(self.base + "resources/?all=1").data["count"], 2)


class CatalogApiTests(ServiceClientMixin, APITestCase):
    csv_data = CATALOG

    def answer(self):
        return catalog_answer()

    def test_instant_mode_confirms_immediately_and_respects_capacity(self):
        igloo = Resource.objects.get(upload=self.upload, name="이글루A")
        self.assertEqual(igloo.capacity, 5)
        for index in range(5):
            response = self.mutate("bookings/", {"persona": "booker", "resource_id": str(igloo.id), "date": future(7), "end_date": future(8), "booker": f"손님{index}"})
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["status"], "approved")
        self.assertEqual(self.config["booking"]["unit"], "stay")  # 캠핑장
        full = self.mutate("bookings/", {"persona": "booker", "resource_id": str(igloo.id), "date": future(7), "end_date": future(8), "booker": "손님6"})
        self.assertEqual(full.status_code, 400)
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "resource_id": str(igloo.id), "date": future(8), "end_date": future(9), "booker": "손님7"}).status_code, 201)
        past = self.mutate("bookings/", {"persona": "booker", "resource_id": str(igloo.id), "date": "2020-01-01", "end_date": "2020-01-02", "booker": "옛날"})
        self.assertEqual(past.status_code, 400)
        self.assertEqual(self.client.get(self.base + "bookings/stats/?persona=admin").data["new"], 6)


class SlotsApiTests(ServiceClientMixin, APITestCase):
    csv_data = SLOTS

    def answer(self):
        return slots_answer()

    def test_booking_by_slot_counts_attendance_against_capacity(self):
        slots = self.client.get(self.base + "slots/").data
        self.assertEqual(slots["count"], 6)
        slot = Slot.objects.get(upload=self.upload, imported_count=17)
        updated = self.mutate(f"slots/{slot.id}/", {"persona": "admin", "capacity": 18}, "patch")
        self.assertEqual(updated.data["remaining"], 1)
        booked = self.mutate("bookings/", {"persona": "booker", "slot_id": str(slot.id), "booker": "참가자"})
        self.assertEqual(booked.status_code, 201, booked.data)
        self.assertEqual((booked.data["time_slot"], booked.data["date"]), ("오전10시~12시", "2026-04-16"))
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "slot_id": str(slot.id), "booker": "늦은 참가자"}).status_code, 400)
        listed = self.client.get(self.base + f"slots/?resource={slot.resource_id}").data["slots"]
        self.assertEqual(next(item for item in listed if item["id"] == str(slot.id))["remaining"], 0)
        closed = self.mutate(f"slots/{slot.id}/", {"persona": "admin", "closed": True}, "patch")
        self.assertTrue(closed.data["closed"])
        self.assertEqual(self.mutate(f"slots/{slot.id}/", {"persona": "admin"}, "delete").status_code, 400)
        new_slot = self.mutate("slots/", {"persona": "admin", "resource_id": str(slot.resource_id), "date": future(10),
                                          "time_slot": "오후2시~4시", "capacity": 20})
        self.assertEqual(new_slot.status_code, 201)
        self.assertEqual(self.mutate(f"slots/{new_slot.data['id']}/", {"persona": "admin"}, "delete").data, {"deleted": True})
        self.assertEqual(self.mutate("slots/", {"persona": "booker", "resource_id": str(slot.resource_id), "date": future(10)}).status_code, 400)


class PaymentApiTests(ServiceClientMixin, APITestCase):
    from .test_reservation_service import CODED as csv_data  # noqa: F401

    def answer(self):
        from .test_reservation_service import coded_answer
        return coded_answer()

    def test_finance_sees_payments_and_marks_them_but_cannot_approve(self):
        unpaid = self.client.get(self.base + "bookings/?persona=finance&payment=unpaid").data
        self.assertEqual(unpaid["count"], 3)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=finance&payment=paid").data["count"], 2)
        booking = unpaid["bookings"][0]["id"]
        self.assertEqual(self.mutate(f"bookings/{booking}/", {"persona": "finance", "action": "approve"}, "patch").status_code, 400)
        paid = self.mutate(f"bookings/{booking}/", {"persona": "finance", "action": "mark_paid", "note": "현금"}, "patch")
        self.assertEqual(paid.status_code, 200, paid.data)
        self.assertEqual(paid.data["payment"], "결제완료")
        self.assertEqual(paid.data["events"][-1]["note"], "결제완료 · 현금")
        self.assertEqual(self.client.get(self.base + "bookings/?persona=finance&payment=paid").data["count"], 3)
        self.assertEqual(self.mutate(f"bookings/{booking}/", {"persona": "booker", "action": "mark_paid"}, "patch").status_code, 400)


class ResourceFacetTests(ServiceClientMixin, APITestCase):
    from .test_reservation_service import CATALOG as csv_data  # noqa: F401

    def answer(self):
        from .test_reservation_service import catalog_answer
        return catalog_answer()

    def test_facets_come_from_attributes_and_filter_the_list(self):
        facets = self.client.get(self.base + "resources/facets/").data
        self.assertEqual(facets["total"], 5)
        self.assertEqual([group["name"] for group in facets["groups"]], ["A구역", "B구역", "C구역"])
        kinds = next(facet for facet in facets["facets"] if facet["label"] == "시설분류")
        self.assertEqual(sum(item["count"] for item in kinds["values"]), 5)
        self.assertIn("정원", [item["label"] for item in facets["ranges"]])
        self.assertIn("평일금액", [item["label"] for item in facets["ranges"]])
        filtered = self.client.get(self.base + "resources/?f=시설분류:카라반").data
        self.assertEqual((filtered["count"], filtered["resources"][0]["name"], filtered["filtering"]), (1, "카라반B", True))
        roomy = self.client.get(self.base + "resources/?min=정원:6").data
        self.assertEqual(sorted(item["name"] for item in roomy["resources"]), ["글램핑C", "오토캠핑C", "일반캠핑A"])
        cheap = self.client.get(self.base + "resources/?max=평일금액:20000&group=" + facets["groups"][2]["id"]).data
        self.assertEqual([item["name"] for item in cheap["resources"]], ["오토캠핑C"])
        self.assertEqual(self.client.get(self.base + "resources/?max=평일금액:abc").status_code, 400)
