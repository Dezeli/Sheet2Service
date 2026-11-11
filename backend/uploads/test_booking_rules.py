"""Booking rules: time modes, sessions, hourly blocks, capacity by bookings or people, closed weekdays. No model call."""
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from .booking_rules import RuleError, default_rules, validate_rules
from .models import Booking, Resource
from .reservation_service import phone_digits
from .test_fixtures import ServiceClientMixin
from .test_reservation_service import CATALOG, catalog_answer


def monday(weeks=1):
    today = timezone.localdate()
    return today + timedelta(days=7 * weeks - today.weekday())


def rules(**changes):
    base = {"timeMode": "day", "sessions": [{"label": "오전", "start": "09:00", "end": "12:00"},
                                            {"label": "오후", "start": "13:00", "end": "18:00"}],
            "hourly": {"open": "09:00", "close": "18:00", "step": 60, "minSteps": 1, "maxSteps": 0},
            "capacityBy": "bookings", "limit": 1, "closedWeekdays": []}
    base.update(changes)
    return base


class RuleDerivationTests(SimpleTestCase):
    def config(self, **booking):
        return {"sheetKind": "booking_records", "columnLabels": ["객실", "수용인원"],
                "booking": {"unit": "time_slot", "capacityColumn": 0, "slotOptions": [], "hourRange": [9, 21], **booking}}

    def test_sessions_come_from_recorded_slots_and_capacity_wording_picks_the_count(self):
        derived = default_rules(self.config(slotOptions=["오후2시~4시", "오전10시~12시", "종일", "1부"]))
        self.assertEqual(derived["sessions"], [{"label": "오전10시~12시", "start": "10:00", "end": "12:00"},
                                               {"label": "오후2시~4시", "start": "14:00", "end": "16:00"},
                                               {"label": "1부", "start": "", "end": ""}])
        self.assertEqual((derived["hourly"]["open"], derived["hourly"]["close"]), ("09:00", "21:00"))
        self.assertEqual((derived["capacityBy"], derived["limit"]), ("bookings", 1))
        self.assertEqual(default_rules(self.config(capacityColumn=2, partySizeMax=6))["capacityBy"], "people")
        self.assertEqual(len(default_rules(self.config())["sessions"]), 2)  # 오전·오후 when the sheet shows none

    def test_validation_names_the_problem(self):
        self.assertEqual(validate_rules(rules())["limit"], 1)
        for bad, word in ((rules(timeMode="hour"), "시간 단위"), (rules(limit=0), "기본 한도"),
                          (rules(timeMode="time_slot", sessions=[]), "하나 이상"),
                          (rules(sessions=[{"label": "오전", "start": "12:00", "end": "09:00"}]), "이후"),
                          (rules(sessions=[{"label": "A", "start": "", "end": ""}, {"label": "A", "start": "", "end": ""}]), "두 번"),
                          (rules(hourly={"open": "09:00", "close": "18:00", "step": 45, "minSteps": 1, "maxSteps": 0}), "간격"),
                          (rules(hourly={"open": "09:00", "close": "18:00", "step": 60, "minSteps": 3, "maxSteps": 2}), "최대"),
                          (rules(closedWeekdays=list(range(7))), "모든 요일")):
            with self.assertRaises(RuleError) as caught:
                validate_rules(bad)
            self.assertIn(word, str(caught.exception))


class BookingRulesApiTests(ServiceClientMixin, APITestCase):
    csv_data = CATALOG

    def answer(self):
        return catalog_answer()

    def setUp(self):
        super().setUp()
        group = Resource.objects.get(upload=self.upload, path="A구역")
        self.room = Resource.objects.create(upload=self.upload, parent=group, level=1, name="회의실", path="A구역 / 회의실")
        self.day = monday()

    def set_rules(self, **changes):
        response = self.mutate("booking-rules/", {"persona": "admin", "rules": rules(**changes)}, "patch")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["rules"]

    def book(self, **body):
        return self.mutate("bookings/", {"persona": "booker", "password": "1234", "resource_id": str(self.room.id), "booker": "예약자",
                                         "phone": "010-1234-5678", **body})

    def at(self, clock, day=None):
        return f"{(day or self.day).isoformat()}T{clock}:00+09:00"

    def test_rules_are_derived_then_saved_by_an_admin_only(self):
        current = self.client.get(self.base + "booking-rules/").data
        self.assertEqual(current["rules"]["timeMode"], "stay")  # 캠핑장
        self.assertEqual(current["rules"]["capacityBy"], "bookings")  # 시설수 counts places, not people
        self.assertEqual(self.mutate("booking-rules/", {"persona": "booker", "rules": rules()}, "patch").status_code, 400)
        self.assertEqual(self.mutate("booking-rules/", {"persona": "admin", "rules": rules(limit=-1)}, "patch").status_code, 400)
        self.set_rules(timeMode="time_range")
        service = self.client.get(self.base + "service/").data["service"]
        self.assertEqual((service["booking"]["unit"], service["booking"]["rules"]["timeMode"]), ("time_range", "time_range"))

    def test_hourly_blocks_follow_hours_step_and_length_and_never_overlap(self):
        self.set_rules(timeMode="time_range", hourly={"open": "09:00", "close": "18:00", "step": 60, "minSteps": 1, "maxSteps": 3})
        first = self.book(starts_at=self.at("10:00"), ends_at=self.at("12:00"))
        self.assertEqual(first.status_code, 201, first.data)
        overlap = self.book(starts_at=self.at("11:00"), ends_at=self.at("13:00"))
        self.assertEqual(overlap.status_code, 400)
        self.assertIn("가득", overlap.data["detail"])
        self.assertEqual(self.book(starts_at=self.at("12:00"), ends_at=self.at("13:00")).status_code, 201)  # back to back
        for start, end, word in (("08:00", "09:00", "운영 시간"), ("13:30", "14:30", "60분 단위"), ("13:00", "17:00", "180분까지")):
            response = self.book(starts_at=self.at(start), ends_at=self.at(end))
            self.assertEqual(response.status_code, 400)
            self.assertIn(word, response.data["detail"])
        day = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&date={self.day}").data
        taken = [block["start"] for block in day["blocks"] if not block["available"]]
        self.assertEqual(taken, ["10:00", "11:00", "12:00"])
        self.assertFalse(day["full"])

    def test_sessions_block_only_their_own_time_and_reject_other_texts(self):
        self.set_rules(timeMode="time_slot")
        morning = self.book(date=self.day.isoformat(), time_slot="오전")
        self.assertEqual(morning.status_code, 201, morning.data)
        self.assertEqual(morning.data["starts_at"][11:16], "09:00")
        self.assertEqual(self.book(date=self.day.isoformat(), time_slot="오전").status_code, 400)
        self.assertEqual(self.book(date=self.day.isoformat(), time_slot="10:00~11:00").status_code, 400)
        state = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&date={self.day}").data
        self.assertEqual([(item["label"], item["available"]) for item in state["sessions"]], [("오전", False), ("오후", True)])
        self.assertEqual(self.book(date=self.day.isoformat(), time_slot="오후").status_code, 201)
        month = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&month={self.day:%Y-%m}").data
        self.assertTrue(month["days"][self.day.isoformat()]["full"])

    def test_a_limit_above_one_takes_that_many_bookings_at_once(self):
        self.set_rules(limit=2)
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 201)
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 201)
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 400)
        self.room.capacity = 3  # a resource's own number overrides the default
        self.room.save(update_fields=["capacity"])
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 201)

    def test_people_mode_counts_party_sizes(self):
        self.set_rules(capacityBy="people", limit=5)
        self.assertEqual(self.book(date=self.day.isoformat(), party_size=3).status_code, 201)
        over = self.book(date=self.day.isoformat(), party_size=3)
        self.assertEqual(over.status_code, 400)
        self.assertIn("2명까지", over.data["detail"])
        self.assertEqual(self.book(date=self.day.isoformat(), party_size=6).status_code, 400)
        self.assertEqual(self.book(date=self.day.isoformat(), party_size=2).status_code, 201)
        day = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&date={self.day}").data
        self.assertEqual((day["remaining"], day["full"]), (0, True))

    def test_closed_weekdays_and_stays_over_full_nights(self):
        self.set_rules(timeMode="stay", closedWeekdays=[6])
        sunday = self.day + timedelta(days=6)
        self.assertIn("일요일", self.book(date=sunday.isoformat(), end_date=(sunday + timedelta(days=1)).isoformat()).data["detail"])
        month = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&month={sunday:%Y-%m}").data
        self.assertTrue(month["days"][sunday.isoformat()]["closed"])
        self.assertEqual(self.book(date=(self.day + timedelta(days=1)).isoformat(), end_date=(self.day + timedelta(days=2)).isoformat()).status_code, 201)
        across = self.book(date=self.day.isoformat(), end_date=(self.day + timedelta(days=3)).isoformat())
        self.assertEqual(across.status_code, 400)  # Tuesday night is taken
        self.assertEqual(self.book(date=self.day.isoformat(), end_date=(self.day + timedelta(days=1)).isoformat()).status_code, 201)

    def test_reopening_a_cancelled_booking_needs_its_place_back(self):
        self.set_rules()
        first = self.book(date=self.day.isoformat())
        self.mutate(f"bookings/{first.data['id']}/unlock/", {"password": "1234"})
        self.assertEqual(self.mutate(f"bookings/{first.data['id']}/", {"persona": "booker", "action": "cancel"}, "patch").status_code, 200)
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 201)
        reopened = self.mutate(f"bookings/{first.data['id']}/", {"persona": "operator", "action": "reopen"}, "patch")
        self.assertEqual(reopened.status_code, 400)
        self.assertIn("다시 열 수 없습니다", reopened.data["detail"])
        self.assertEqual(Booking.objects.get(pk=first.data["id"]).status, "cancelled")


class BranchRulesApiTests(ServiceClientMixin, APITestCase):
    """One sheet mixes rentals and classes, so a branch can book under its own rules."""
    csv_data = CATALOG

    def answer(self):
        return catalog_answer()

    def setUp(self):
        super().setUp()
        self.group = Resource.objects.get(upload=self.upload, path="A구역")
        self.room = Resource.objects.create(upload=self.upload, parent=self.group, level=1, name="체험교실", path="A구역 / 체험교실")
        self.other = Resource.objects.get(upload=self.upload, name="카라반B")
        self.day = monday()

    def book(self, **body):
        return self.mutate("bookings/", {"persona": "booker", "password": "1234", "resource_id": str(self.room.id), "booker": "홍길동",
                                         "phone": "010-1234-5678", **body})

    def test_a_branch_carries_its_own_sessions_and_one_slot_per_person(self):
        hourly = [{"label": f"{hour}:00~{hour + 1}:00", "start": f"{hour}:00", "end": f"{hour + 1}:00"} for hour in range(10, 16)]
        saved = self.mutate("booking-rules/", {"persona": "admin", "resource_id": str(self.group.id),
                                               "rules": rules(timeMode="time_slot", sessions=hourly, capacityBy="people", limit=10,
                                                              closedWeekdays=[0, 1, 2, 3, 4, 6], perPerson={"limit": 1, "per": "day"})}, "patch")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["source"]["path"], "A구역")
        self.assertEqual([item["path"] for item in saved.data["overrides"]], ["A구역"])
        inherited = self.client.get(self.base + f"booking-rules/?resource={self.room.id}").data
        self.assertEqual((inherited["rules"]["timeMode"], inherited["source"]["name"]), ("time_slot", "A구역"))
        untouched = self.client.get(self.base + f"booking-rules/?resource={self.other.id}").data
        self.assertEqual((untouched["rules"]["timeMode"], untouched["source"]), ("stay", None))

        saturday = (self.day + timedelta(days=5)).isoformat()
        self.assertIn("휴무", self.book(date=self.day.isoformat(), time_slot="10:00~11:00").data["detail"])
        first = self.book(date=saturday, time_slot="10:00~11:00", party_size=2)
        self.assertEqual(first.status_code, 201, first.data)
        again = self.book(date=saturday, time_slot="11:00~12:00")
        self.assertEqual(again.status_code, 400)
        self.assertIn("하루에 1건", again.data["detail"])
        # a person is their phone number, whoever enters it
        self.assertEqual(self.book(persona="admin", date=saturday, time_slot="11:00~12:00", booker="홍 길동", phone="01012345678").status_code, 400)
        self.assertEqual(self.book(date=saturday, time_slot="11:00~12:00", booker="김영희", phone="010-9876-5432").status_code, 201)
        state = self.client.get(self.base + f"bookings/availability/?persona=booker&resource={self.room.id}&date={saturday}").data
        self.assertEqual([item["remaining"] for item in state["sessions"][:2]], [8, 9])

        removed = self.mutate("booking-rules/", {"persona": "admin", "resource_id": str(self.group.id), "rules": None}, "patch")
        self.assertEqual((removed.data["source"], removed.data["overrides"]), (None, []))
        self.assertEqual(self.client.get(self.base + f"booking-rules/?resource={self.room.id}").data["rules"]["timeMode"], "stay")

    def test_upcoming_limit_counts_live_bookings_from_today(self):
        self.mutate("booking-rules/", {"persona": "admin", "resource_id": str(self.room.id),
                                       "rules": rules(limit=5, perPerson={"limit": 2, "per": "upcoming"})}, "patch")
        self.assertEqual(self.book(date=self.day.isoformat()).status_code, 201)
        second = self.book(date=(self.day + timedelta(days=1)).isoformat())
        self.assertEqual(second.status_code, 201)
        self.assertIn("2건까지", self.book(date=(self.day + timedelta(days=2)).isoformat()).data["detail"])
        self.mutate(f"bookings/{second.data['id']}/unlock/", {"password": "1234"})
        self.mutate(f"bookings/{second.data['id']}/", {"persona": "booker", "action": "cancel"}, "patch")
        self.assertEqual(self.book(date=(self.day + timedelta(days=2)).isoformat()).status_code, 201)
        self.assertEqual(self.mutate("booking-rules/", {"persona": "admin", "resource_id": str(self.room.id),
                                                        "rules": rules(perPerson={"limit": 1, "per": "week"})}, "patch").status_code, 400)


class PhoneIdentityTests(ServiceClientMixin, APITestCase):
    """Without sign-in a booker is a name and a phone number: required, used for the limit, lookup and cancelling."""
    csv_data = CATALOG

    def answer(self):
        return catalog_answer()

    def setUp(self):
        super().setUp()
        group = Resource.objects.get(upload=self.upload, path="A구역")
        self.room = Resource.objects.create(upload=self.upload, parent=group, level=1, name="회의실", path="A구역 / 회의실")
        self.mutate("booking-rules/", {"persona": "admin", "rules": rules(limit=5)}, "patch")
        self.day = monday().isoformat()

    def book(self, **body):
        return self.mutate("bookings/", {"persona": "booker", "password": "1234", "resource_id": str(self.room.id), "booker": "홍길동", "date": self.day, **body})

    def test_phone_numbers_are_read_loosely_and_stored_as_digits(self):
        self.assertEqual(phone_digits("010-1234-5678"), "01012345678")
        self.assertEqual(phone_digits("+82 10 1234 5678"), "01012345678")
        self.assertEqual(phone_digits("02)123-4567"), "021234567")
        self.assertEqual(phone_digits("1234"), "")
        self.assertIn("전화번호", self.book().data["detail"])
        self.assertIn("010-1234-5678처럼", self.book(phone="12-34").data["detail"])
        self.assertEqual(self.book(phone="010 1234 5678", booker="").status_code, 400)  # the name is required too
        created = self.book(phone="010 1234 5678")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["phone"], "010-1234-5678")
        self.assertEqual(Booking.objects.get(pk=created.data["id"]).phone, "01012345678")

    def test_reviewers_see_masked_numbers_in_lists_and_whole_ones_in_detail(self):
        created = self.book(phone="01012345678")
        listed = self.client.get(self.base + "bookings/?persona=operator&q=5678").data
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["bookings"][0]["phone"], "010-****-5678")
        detail = self.client.get(self.base + f"bookings/{created.data['id']}/?persona=operator").data
        self.assertEqual(detail["phone"], "010-1234-5678")

    def test_a_booking_needs_a_four_digit_pin_and_stores_only_its_hash(self):
        self.assertIn("비밀번호", self.book(phone="01012345678", password="").data["detail"])
        self.assertIn("4자리", self.book(phone="01012345678", password="12a4").data["detail"])
        created = self.book(phone="01012345678", password="4321")
        stored = Booking.objects.get(pk=created.data["id"]).password
        self.assertTrue(stored and "4321" not in stored)
        self.assertNotIn("password", created.data)

    def test_my_bookings_are_masked_until_the_pin_opens_one(self):
        created = self.book(phone="01052341231", booker="홍길동", password="4321")
        self.assertTrue(created.data["mine"])  # the reply to the booking itself
        listed = self.client.get(self.base + "bookings/?persona=booker").data["bookings"][0]
        self.assertEqual((listed["booker"], listed["phone"], listed["locked"], listed["mine"]), ("홍*동", "010-5***-1231", True, False))
        path = f"bookings/{created.data['id']}/"
        self.assertEqual(self.client.get(self.base + path + "?persona=booker").status_code, 400)
        self.assertEqual(self.mutate(path, {"persona": "booker", "action": "cancel"}, "patch").status_code, 400)
        self.assertEqual(self.mutate(path + "unlock/", {"password": "0000"}).status_code, 400)
        opened = self.mutate(path + "unlock/", {"password": "4321"})
        self.assertEqual((opened.status_code, opened.data["booker"], opened.data["phone"]), (200, "홍길동", "010-5234-1231"))
        self.assertEqual(self.client.get(self.base + path + "?persona=booker").status_code, 200)
        listed = self.client.get(self.base + "bookings/?persona=booker").data["bookings"][0]
        self.assertEqual((listed["booker"], listed["mine"]), ("홍길동", True))
        self.assertEqual(self.mutate(path, {"persona": "booker", "action": "cancel"}, "patch").data["status"], "cancelled")

    def test_another_device_finds_by_name_and_phone_then_opens_with_the_pin(self):
        created = self.book(phone="01012345678", password="4321")
        Booking.objects.filter(pk=created.data["id"]).update(created_by_session="another-device")
        self.assertEqual(self.client.get(self.base + "bookings/?persona=booker").data["count"], 0)
        found = self.client.get(self.base + "bookings/?persona=booker&name=홍길동&phone=010-1234-5678").data
        self.assertEqual((found["count"], found["bookings"][0]["booker"], found["bookings"][0]["purpose"]), (1, "홍*동", ""))
        self.assertEqual(self.client.get(self.base + "bookings/?persona=booker&phone=010-1234-5678").data["count"], 1)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=booker&name=홍길동").data["count"], 1)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=booker&name=김철수").data["count"], 0)
        self.assertEqual(self.client.get(self.base + "bookings/?persona=booker&phone=12").status_code, 400)
        self.assertEqual(self.mutate(f"bookings/{created.data['id']}/unlock/", {"password": "4321"}).status_code, 200)

    def test_five_wrong_pins_lock_that_booking(self):
        from django.core.cache import cache
        cache.clear()
        created = self.book(phone="01012345678", password="4321")
        path = f"bookings/{created.data['id']}/unlock/"
        for _ in range(5):
            self.assertEqual(self.mutate(path, {"password": "0000"}).status_code, 400)
        self.assertIn("10분", self.mutate(path, {"password": "4321"}).data["detail"])
        cache.clear()

    def test_a_booker_changes_party_and_request_within_capacity(self):
        self.mutate("booking-rules/", {"persona": "admin", "rules": rules(limit=4, capacityBy="people")}, "patch")
        created = self.book(phone="01012345678", password="4321", party_size=2)
        path = f"bookings/{created.data['id']}/"
        self.assertEqual(self.mutate(path, {"persona": "booker", "action": "edit", "party_size": 3}, "patch").status_code, 400)  # PIN first
        self.mutate(path + "unlock/", {"password": "4321"})
        self.assertIn("4명", self.mutate(path, {"persona": "booker", "action": "edit", "party_size": 5}, "patch").data["detail"])
        edited = self.mutate(path, {"persona": "booker", "action": "edit", "party_size": 4, "purpose": "휠체어 1대"}, "patch")
        self.assertEqual((edited.status_code, edited.data["party_size"], edited.data["purpose"]), (200, 4, "휠체어 1대"))
        self.assertIn("인원 2→4명", edited.data["events"][-1]["note"])
        self.assertEqual(self.mutate(path, {"persona": "booker", "action": "edit", "date": self.day}, "patch").status_code, 400)
        self.assertEqual(self.mutate(path, {"persona": "operator", "action": "edit", "party_size": 1}, "patch").status_code, 400)


class SettledScheduleTests(ServiceClientMixin, APITestCase):
    """Items whose records share one period enrol into it; fees come from the records; free sheets have no payment desk."""
    from .test_reservation_understanding import BOOKINGS as csv_data  # noqa: F401

    def answer(self):
        from .test_reservation_understanding import model_answer
        return model_answer()

    def test_a_shared_period_becomes_the_items_session_and_bookers_enrol_into_it(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        from .models import Slot
        from .reservation_service import settle_service
        course = Resource.objects.filter(upload=self.upload, children__isnull=True).first()
        free = Resource.objects.filter(upload=self.upload, children__isnull=True).exclude(pk=course.pk).first()
        Booking.objects.filter(upload=self.upload).update(slot=None)
        Slot.objects.filter(upload=self.upload).delete()
        start = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=7), datetime.min.time())) + timedelta(hours=19)
        for name in ("가", "나", "다", "라", "마"):  # a course: everyone on the same weeks, 19:00~21:00
            Booking.objects.create(upload=self.upload, resource=course, booker=name, status="approved",
                                   starts_at=start, ends_at=start + timedelta(days=30, hours=2), amount=0)
        Booking.objects.create(upload=self.upload, resource=course, booker="바", status="approved", starts_at=start,
                               ends_at=start + timedelta(hours=1), amount=0)
        for hours in (1, 3):  # a room: every booking at its own time
            Booking.objects.create(upload=self.upload, resource=free, booker="사", status="approved",
                                   starts_at=start + timedelta(hours=hours), ends_at=start + timedelta(hours=hours + 1))
        config = self.upload.service_config
        config.pop("settled", None)
        config["booking"].update(amountColumn=config["booking"].get("amountColumn") or 1, paymentColumn=config["booking"].get("paymentColumn") or 1)
        self.upload.service_config = config
        self.upload.save(update_fields=["service_config"])
        config = settle_service(self.upload)
        session = Slot.objects.get(upload=self.upload, resource=course)
        self.assertEqual(session.time_slot, "19:00~21:00")
        self.assertEqual(Booking.objects.filter(slot=session).count(), 5)
        self.assertFalse(Slot.objects.filter(upload=self.upload, resource=free).exists())
        self.assertNotIn("finance", [persona["id"] for persona in config["personas"]])  # every record is free
        course.refresh_from_db()
        self.assertEqual(course.attributes["이용료"], "무료")
        body = {"persona": "booker", "password": "1234", "phone": "010-1234-5678", "booker": "신청자", "resource_id": str(course.id),
                "date": session.date.isoformat()}
        self.assertIn("회차를 골라", self.mutate("bookings/", body).data["detail"])
        enrolled = self.mutate("bookings/", {**body, "slot_id": str(session.id)})
        self.assertEqual(enrolled.status_code, 201, enrolled.data)
        self.assertEqual((enrolled.data["amount"], enrolled.data["payment"]), ("0", "무료"))
        Slot.objects.filter(pk=session.pk).update(date=timezone.localdate() - timedelta(days=1))
        self.assertIn("모집이 끝난", self.mutate("bookings/", {**body, "slot_id": str(session.id), "phone": "010-2222-3333"}).data["detail"])

    def test_a_course_gets_a_session_per_term_and_an_event_one_per_showing(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        from .models import Slot
        from .reservation_service import _fixed_sessions
        Booking.objects.filter(upload=self.upload).update(slot=None)
        Slot.objects.filter(upload=self.upload).delete()
        course, talk, room = list(Resource.objects.filter(upload=self.upload, children__isnull=True)[:3])
        Booking.objects.filter(resource__in=[course, talk, room]).delete()
        at = lambda day, hour: timezone.make_aware(datetime(2026, 3, 1) + timedelta(days=day, hours=hour))
        for start in (0, 180):  # spring and autumn, 14:00~16:00 over ten weeks
            for name in ("가", "나"):
                Booking.objects.create(upload=self.upload, resource=course, booker=name, status="approved",
                                       starts_at=at(start, 14), ends_at=at(start + 70, 16))
        Booking.objects.create(upload=self.upload, resource=course, booker="다", status="approved", starts_at=at(360, 14), ends_at=at(430, 16))
        for hour in (14, 19):  # a talk given twice in one day
            for name in ("가", "나", "다"):
                Booking.objects.create(upload=self.upload, resource=talk, booker=name, status="approved", starts_at=at(5, hour), ends_at=at(5, hour + 2))
        for hour in (9, 11, 13, 15):  # a room: every booking at its own time
            Booking.objects.create(upload=self.upload, resource=room, booker="라", status="approved", starts_at=at(7, hour), ends_at=at(7, hour + 1))
        _fixed_sessions(self.upload)
        self.assertEqual([slot.time_slot for slot in Slot.objects.filter(resource=course)], ["14:00~16:00"] * 3)
        self.assertEqual(Slot.objects.filter(resource=talk).count(), 2)
        self.assertFalse(Slot.objects.filter(resource=room).exists())
        self.assertEqual(Booking.objects.filter(resource=course, slot__isnull=False).count(), 5)
