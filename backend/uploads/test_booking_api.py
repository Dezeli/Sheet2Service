"""Resources, slots and bookings through the API, as each persona. No model call."""
from datetime import date, timedelta

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
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(org.id), "date": future(3),
                                                   "booker": "홍길동"}).status_code, 400)  # must pick the leaf
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id),
                                                   "booker": "홍길동"}).status_code, 400)  # date model needs a date
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id), "date": future(3)}).status_code, 400)
        self.assertEqual(self.config["booking"]["unit"], "stay")  # 숙박일자 + 객실
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id), "date": future(3),
                                                   "end_date": future(3), "booker": "홍길동"}).status_code, 400)  # a stay needs a night
        created = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id), "date": future(3), "end_date": future(5),
                                            "booker": "홍길동", "party_size": 3, "purpose": "가족 여행"})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], "requested")  # approval mode
        self.assertTrue(created.data["mine"])
        self.assertEqual(created.data["events"][0]["to"], "requested")
        # the same room on the same day is taken (capacity defaults to one)
        second = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id), "date": future(4), "end_date": future(6), "booker": "김철수"})
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(room.id), "date": future(5), "end_date": future(7),
                                                   "booker": "박영희"}).status_code, 201)  # checkout day is free again
        self.assertEqual(second.status_code, 400)
        self.assertIn("가득", second.data["detail"])
        mine = self.client.get(self.base + "bookings/?persona=booker").data
        self.assertEqual(mine["count"], 2)
        booking_id = created.data["id"]
        self.assertEqual(self.mutate(f"bookings/{booking_id}/", {"persona": "booker", "action": "approve"}, "patch").status_code, 400)
        rejected = self.mutate(f"bookings/{booking_id}/", {"persona": "operator", "action": "reject"}, "patch")
        self.assertEqual(rejected.status_code, 400)  # a reason is required
        approved = self.mutate(f"bookings/{booking_id}/", {"persona": "operator", "action": "approve", "note": "확인"}, "patch")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual([event["to"] for event in approved.data["events"]], ["requested", "approved"])
        self.assertEqual(self.mutate(f"bookings/{booking_id}/", {"persona": "operator", "action": "approve"}, "patch").status_code, 400)
        self.assertEqual(self.mutate(f"bookings/{booking_id}/", {"persona": "booker", "action": "cancel"}, "patch").status_code, 400)  # PIN first
        self.assertEqual(self.mutate(f"bookings/{booking_id}/unlock/", {"password": "1234"}).status_code, 200)
        cancelled = self.mutate(f"bookings/{booking_id}/", {"persona": "booker", "action": "cancel"}, "patch")
        self.assertEqual(cancelled.data["status"], "cancelled")
        other = APIClient(enforce_csrf_checks=True)
        self.assertEqual(other.get(self.base + "bookings/?persona=booker").status_code, 404)
        self.assertEqual(self.client.post(self.base + "bookings/", {"persona": "booker"}, format="json").status_code, 403)

    def test_the_service_title_defaults_to_its_subject_and_admins_rename_it(self):
        url = self.base + "service/"
        self.assertEqual(self.client.get(url).data["service"]["title"], self.config["subject"])
        self.assertEqual(self.mutate("service/", {"persona": "booker", "title": "새 이름"}, "patch").status_code, 400)
        self.assertEqual(self.mutate("service/", {"persona": "admin", "title": " "}, "patch").status_code, 400)
        renamed = self.mutate("service/", {"persona": "admin", "title": "  상주 통합예약  "}, "patch")
        self.assertEqual(renamed.data["service"]["title"], "상주 통합예약")
        self.assertEqual(self.client.get(url).data["service"]["title"], "상주 통합예약")

    def test_bulk_action_applies_where_it_fits_and_skips_the_rest(self):
        waiting = [item["id"] for item in self.client.get(self.base + "bookings/?persona=operator&status=requested").data["bookings"]]
        settled = self.client.get(self.base + "bookings/?persona=operator&status=approved").data["bookings"][0]["id"]
        url = "bookings/bulk/"
        self.assertEqual(self.mutate(url, {"persona": "booker", "action": "approve", "ids": waiting}).status_code, 400)
        self.assertEqual(self.mutate(url, {"persona": "operator", "action": "approve", "ids": []}).status_code, 400)
        self.assertEqual(self.mutate(url, {"persona": "operator", "action": "reject", "ids": waiting}).status_code, 400)  # needs a reason
        result = self.mutate(url, {"persona": "operator", "action": "approve", "ids": [*waiting, settled]})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual((result.data["done"], result.data["skipped"]), (2, 1))
        self.assertEqual(Booking.objects.filter(pk__in=waiting, status="approved").count(), 2)
        self.assertEqual(Booking.objects.get(pk=waiting[0]).events.count(), 1)

    def test_admin_list_filters_stats_and_imported_records(self):
        everything = self.client.get(self.base + "bookings/?persona=operator").data
        self.assertEqual(everything["count"], 10)
        self.assertTrue(all(item["imported"] for item in everything["bookings"]))
        waiting = self.client.get(self.base + "bookings/?persona=operator&status=requested").data
        self.assertEqual(waiting["count"], 2)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=operator&q=크낙새").data["count"], 3)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=operator&status=bogus").status_code, 400)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=nobody").status_code, 400)
        approved = self.mutate(f"bookings/{waiting['bookings'][0]['id']}/", {"persona": "operator", "action": "approve"}, "patch")
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(approved.data["status_label"], "")
        stats = self.client.get(self.base + "bookings/stats/?persona=operator").data
        self.assertEqual((stats["total"], stats["counts"]["requested"], stats["counts"]["approved"], stats["imported"]), (10, 1, 5, 10))
        self.assertEqual(stats["top_resources"][0]["count"], 3)
        self.assertEqual(set(stats["payments"]), {"paid", "unpaid", "unpaid_amount"})

    def test_each_duty_belongs_to_one_role(self):
        personas = {persona["id"]: persona for persona in self.config["personas"]}
        self.assertEqual(list(personas), ["booker", "operator", "field", "admin"])
        owners = {}
        for persona in personas.values():
            for feature in persona["features"]:
                self.assertNotIn(feature, owners, f"{feature} is both {owners.get(feature)}'s and {persona['id']}'s")
                owners[feature] = persona["id"]
        waiting = self.client.get(self.base + "bookings/?persona=operator&status=requested").data["bookings"][0]["id"]
        self.assertEqual(self.mutate(f"bookings/{waiting}/", {"persona": "admin", "action": "approve"}, "patch").status_code, 400)
        self.assertEqual(self.mutate(f"bookings/{waiting}/", {"persona": "field", "action": "approve"}, "patch").status_code, 400)
        self.assertEqual(self.mutate(f"bookings/{waiting}/", {"persona": "operator", "action": "mark_paid"}, "patch").status_code, 400)
        self.assertEqual(self.mutate("resources/", {"persona": "operator", "name": "새 객실"}).status_code, 400)
        approved = self.mutate(f"bookings/{waiting}/", {"persona": "operator", "action": "approve"}, "patch")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(self.mutate(f"bookings/{waiting}/", {"persona": "operator", "action": "check_in"}, "patch").status_code, 400)  # the field's
        self.assertEqual(self.mutate(f"bookings/{waiting}/", {"persona": "field", "action": "check_in"}, "patch").data["status"], "in_use")
        self.assertEqual(self.mutate("service/", {"persona": "operator", "title": "새 이름"}, "patch").status_code, 400)

    def test_operator_sees_only_its_organization(self):
        scopes = self.client.get(self.base + "bookings/scopes/?persona=operator").data
        self.assertEqual((scopes["label"], scopes["values"]), ("기관명", ["변산 자연휴양림", "유명산 자연휴양림"]))
        self.assertEqual(self.client.get(self.base + "bookings/?persona=operator").data["count"], 10)  # the part is optional
        scoped = self.client.get(self.base + "bookings/?persona=operator&scope=변산 자연휴양림").data
        self.assertEqual(scoped["count"], 5)
        self.assertTrue(all(item["resource"]["path"].startswith("변산") for item in scoped["bookings"]))
        self.assertEqual(self.client.get(self.base + "bookings/stats/?persona=operator&scope=변산 자연휴양림").data["total"], 5)
        booking = scoped["bookings"][0]["id"]
        self.assertEqual(self.mutate(f"bookings/{booking}/", {"persona": "operator", "action": "complete"}, "patch").status_code,
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
            response = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(igloo.id), "date": future(7), "end_date": future(8), "booker": f"손님{index}"})
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["status"], "approved")
        self.assertEqual(self.config["booking"]["unit"], "stay")  # 캠핑장
        full = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(igloo.id), "date": future(7), "end_date": future(8), "booker": "손님6"})
        self.assertEqual(full.status_code, 400)
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(igloo.id), "date": future(8), "end_date": future(9), "booker": "손님7"}).status_code, 201)
        past = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "resource_id": str(igloo.id), "date": "2020-01-01", "end_date": "2020-01-02", "booker": "옛날"})
        self.assertEqual(past.status_code, 400)
        self.assertEqual(self.client.get(self.base + "bookings/stats/?persona=operator").data["new"], 6)


class SlotsApiTests(ServiceClientMixin, APITestCase):
    csv_data = SLOTS

    def answer(self):
        return slots_answer()

    def test_booking_by_slot_counts_attendance_against_capacity(self):
        slots = self.client.get(self.base + "slots/").data
        self.assertEqual(slots["count"], 6)
        slot = Slot.objects.get(upload=self.upload, imported_count=17)
        Slot.objects.filter(pk=slot.pk).update(date=date.fromisoformat(future(5)))  # a session still to come
        updated = self.mutate(f"slots/{slot.id}/", {"persona": "admin", "capacity": 18}, "patch")
        self.assertEqual(updated.data["remaining"], 1)
        booked = self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "slot_id": str(slot.id), "booker": "참가자"})
        self.assertEqual(booked.status_code, 201, booked.data)
        self.assertEqual((booked.data["time_slot"], booked.data["date"]), ("오전10시~12시", future(5)))
        self.assertEqual(self.mutate("bookings/", {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "slot_id": str(slot.id), "booker": "늦은 참가자"}).status_code, 400)
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


    def test_card_summary_names_the_next_open_session(self):
        resource = Slot.objects.filter(upload=self.upload).first().resource
        top = resource
        while top.parent_id:
            top = top.parent
        made = self.mutate("slots/", {"persona": "admin", "resource_id": str(resource.id), "date": future(5), "time_slot": "오후2시~4시", "capacity": 20})
        self.assertEqual(made.status_code, 201, made.data)
        listed = self.client.get(self.base + "resources/?summary=1").data["resources"]
        card = next(item for item in listed if item["id"] == str(top.id))["summary"]
        self.assertEqual(card["next_slot"]["id"], made.data["id"])
        self.assertEqual((card["open_slots"], card["next_slot"]["remaining"]), (1, 20))
        self.assertEqual(set(card), {"leaves", "booked", "recent", "upcoming", "next_slot", "open_slots", "slots"})
        self.assertNotIn("summary", self.client.get(self.base + "resources/").data["resources"][0])
        self.assertEqual(self.client.get(self.base + "resources/?size=10").data["size"], 10)
        self.assertEqual(self.client.get(self.base + "resources/?size=7").data["size"], 20)


    def test_items_whose_sessions_are_all_past_say_so_and_come_last(self):
        Slot.objects.filter(upload=self.upload).update(date=date(2020, 1, 1))
        listed = self.client.get(self.base + "resources/?summary=1").data["resources"]
        self.assertTrue(all(item["closed"] for item in listed))
        last = listed[-1]
        leaf = Resource.objects.filter(upload=self.upload, path__startswith=last["path"]).filter(children__isnull=True).first()
        Slot.objects.create(upload=self.upload, resource=leaf, date=date.fromisoformat(future(5)), time_slot="오전", capacity=10)
        listed = self.client.get(self.base + "resources/?summary=1").data["resources"]
        self.assertEqual((listed[0]["id"], listed[0]["closed"]), (last["id"], False))  # open again, so first
        self.assertTrue(all(item["closed"] for item in listed[1:]))


class PaymentApiTests(ServiceClientMixin, APITestCase):
    from .test_reservation_service import CODED as csv_data  # noqa: F401

    def answer(self):
        from .test_reservation_service import coded_answer
        return coded_answer()

    def test_finance_sees_payments_and_marks_them_but_cannot_approve(self):
        unpaid = self.client.get(self.base + "bookings/?persona=finance&payment=unpaid").data
        summary = self.client.get(self.base + "bookings/stats/?persona=finance").data["payments"]
        self.assertEqual(summary["paid"], 2)
        self.assertEqual(summary["unpaid"], unpaid["count"] - sum(item["status"] in ("cancelled", "rejected", "lost") for item in unpaid["bookings"]))
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


class ScheduleApiTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_week_view_lists_bookings_per_resource_and_marks_overbooked_days(self):
        room = Resource.objects.get(upload=self.upload, path="변산 자연휴양림 / 우럭")
        # the imported 2026-03-03 stay is already checked out, so it is not a conflict; two live bookings are
        for name in ("겹침1", "겹침2"):
            Booking.objects.create(upload=self.upload, resource=room, date=date(2026, 3, 5), status="approved", booker=name)
        week = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2026-03-02&days=7").data
        self.assertEqual(week["days"][0], "2026-03-02")
        row = next(item for item in week["resources"] if item["id"] == str(room.id))
        self.assertEqual(len(row["days"]["2026-03-03"]), 1)
        self.assertEqual(len(row["days"]["2026-03-05"]), 2)
        self.assertEqual(row["conflicts"], {"2026-03-05": 1})  # capacity defaults to one
        self.assertEqual(week["conflict_total"], 1)
        self.assertEqual(week["conflicts"][0]["name"], "우럭")
        only = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2026-03-02&days=7&conflicts_only=1").data
        self.assertEqual([item["name"] for item in only["resources"]], ["우럭"])
        self.assertEqual(self.client.get(self.base + "bookings/schedule/?persona=booker").status_code, 400)
        self.assertEqual(self.client.get(self.base + "bookings/schedule/?persona=operator&from=2026-03-02").status_code, 200)  # the part is optional
        scoped = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2026-03-02&scope=유명산 자연휴양림").data
        self.assertTrue(all(item["path"].startswith("유명산") for item in scoped["resources"]))


class ResourceMonthTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_one_resource_over_a_month(self):
        room = Resource.objects.get(upload=self.upload, path="변산 자연휴양림 / 우럭")
        month = self.client.get(self.base + f"bookings/schedule/?persona=operator&from=2026-03-01&days=31&resource={room.id}").data
        self.assertEqual([item["id"] for item in month["resources"]], [str(room.id)])
        self.assertEqual(len(month["days"]), 31)
        self.assertIn("2026-03-03", month["resources"][0]["days"])


class FlatResourceListTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_leaves_in_path_order_filtered_as_you_type(self):
        leaves = self.client.get(self.base + "resources/?flat=leaf").data
        self.assertEqual([item["path"] for item in leaves["resources"]],
                         ["변산 자연휴양림 / 바다향기5", "변산 자연휴양림 / 우럭", "유명산 자연휴양림 / 소나무", "유명산 자연휴양림 / 크낙새"])
        self.assertEqual(self.client.get(self.base + "resources/?flat=any").data["count"], 6)
        self.assertEqual([item["name"] for item in self.client.get(self.base + "resources/?flat=leaf&q=유명산").data["resources"]], ["소나무", "크낙새"])


class BusiestFirstTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_the_week_lists_the_busiest_items_first(self):
        quiet = Resource.objects.get(upload=self.upload, path="유명산 자연휴양림 / 소나무")
        for name in ("가", "나", "다"):
            Booking.objects.create(upload=self.upload, resource=quiet, date=date(2026, 3, 4), status="approved", booker=name)
        week = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2026-03-02&days=7").data
        counts = [row["count"] for row in week["resources"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(week["resources"][0]["name"], "소나무")
        self.assertTrue(all(row["count"] > 0 for row in week["resources"]))
        empty = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2030-01-07&days=7").data
        self.assertEqual(empty["resources"], [])
        self.assertEqual(empty["nearby"]["next"], None)
        self.assertIsNotNone(empty["nearby"]["previous"])  # the latest booked date before an empty week
        early = self.client.get(self.base + "bookings/schedule/?persona=operator&from=2000-01-03&days=7").data
        self.assertIsNotNone(early["nearby"]["next"])
