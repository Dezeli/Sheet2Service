"""Understanding -> service configuration -> materialized resources, slots and bookings. No model call."""
import tempfile
from datetime import date, time

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .analysis import analyze
from .models import Booking, Resource, Slot, Upload
from .reservation_service import (build_service, derive_service, parse_moment, parse_range, parse_time, status_kind,
                                  time_model)
from .reservation_understanding import validate_understanding
from .test_reservation_understanding import BOOKINGS, model_answer

CATALOG = ("구역명,시설명,시설분류,시설수,이용시작시간,이용종료시간,평일금액,도로명주소,관리기관전화번호,데이터기준일자\n"
           "A구역,이글루A,이글루,5,14:00,11:00,50000,정읍시 내장산로 410,063-538-7955,2025-04-08\n"
           "A구역,일반캠핑A,일반캠핑,12,14:00,12:00,15000,정읍시 내장산로 410,063-538-7955,2025-04-08\n"
           "B구역,카라반B,카라반,3,14:00,11:00,100000,정읍시 내장산로 410,063-538-7955,2025-04-08\n"
           "C구역,글램핑C,글램핑,6,14:00,11:00,110000,정읍시 내장산로 410,063-538-7955,2025-04-08\n"
           "C구역,오토캠핑C,오토캠핑,23,14:00,12:00,20000,정읍시 내장산로 410,063-538-7955,2025-04-08\n").encode("utf-8")

WIDE = ("날짜,대공연장,대공연장예약시간,소공연장,소공연장예약시간\n"
        "2017-01-02,의정보고회,10:00~12:00,,\n"
        "2017-01-05,어린이집발표회,17:00~19:00,독서토론회,14:00~16:00\n"
        "2017-01-09,,,시낭송회,19:00~21:00\n"
        "2017-01-12,합창단 정기연주회,19:00~21:00,,\n"
        "2017-01-15,,,,\n"
        "2017-01-20,무용발표회,15:00~17:00,,\n").encode("utf-8")

SLOTS = ("예약일자,시간,코스,유아,초등학생,어른\n"
         "2026-04-02,오전10시~12시,선암호수공원,21,0,0\n"
         "2026-04-16,오전10시~12시,선암호수공원,14,0,3\n"
         "2026-04-20,오후2시~4시,대공원현충탑,0,12,2\n"
         "2026-04-23,오전10시~12시,울산박물관,0,0,5\n"
         "2026-05-01,오후2시~4시,대공원현충탑,8,0,0\n"
         "2026-05-08,오전10시~12시,선암호수공원,10,1,1\n").encode("utf-8")


def catalog_answer():
    return model_answer(sheetKind="resource_catalog", subject="정읍 캠핑장 시설", resourceColumns=[1, 2],
                        columnRoles=["resource_group", "resource", "resource_attribute", "capacity", "start", "end", "amount",
                                     "location", "contact", "ignore"], columnEvidence=[""] * 10,
                        booking={"mode": "instant", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[], questions=[])


def wide_answer():
    return model_answer(sheetKind="wide_schedule", subject="문화회관 공연장", resourceColumns=[2, 4],
                        columnRoles=["date", "wide_resource", "wide_time", "wide_resource", "wide_time"], columnEvidence=[""] * 5,
                        booking={"mode": "approval", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[], questions=[])


def slots_answer():
    return model_answer(sheetKind="schedule_slots", subject="숲해설 프로그램 회차", resourceColumns=[3],
                        columnRoles=["date", "time_slot", "resource", "party_size", "party_size", "party_size"],
                        columnEvidence=[""] * 6,
                        booking={"mode": "instant", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[], questions=[])


class ParsingTests(SimpleTestCase):
    def test_times_ranges_and_moments(self):
        self.assertEqual(parse_time("14:00"), time(14, 0))
        self.assertEqual(parse_time("오후2시"), time(14, 0))
        self.assertEqual(parse_time("오전10시"), time(10, 0))
        self.assertEqual(parse_time("12시"), time(12, 0))
        self.assertEqual(parse_time("09:00:00"), time(9, 0))
        self.assertIsNone(parse_time("종일"))
        self.assertEqual(parse_range("2022-07-29(금)~2022-11-25(금)"), ("2022-07-29(금)", "2022-11-25(금)"))
        self.assertEqual(parse_range("오전10시~12시"), ("오전10시", "12시"))
        self.assertIsNone(parse_range("우럭"))
        self.assertEqual(parse_moment("2026-03-09 14:00").hour, 14)
        self.assertEqual(parse_moment("2022-11-25(금)").date(), date(2022, 11, 25))
        self.assertEqual(parse_moment("15:00", date(2026, 1, 2)).date(), date(2026, 1, 2))
        self.assertIsNone(parse_moment("15:00"))

    def test_status_wording_maps_to_kinds_with_prefixes_and_flags(self):
        states = [{"value": "예약완료", "kind": "approved"}, {"value": "사용자취소", "kind": "cancelled"}]
        self.assertEqual(status_kind("예약완료(등록:23번)", states, default="approved"), "approved")
        self.assertEqual(status_kind("사용자취소", states, default="approved"), "cancelled")
        self.assertEqual(status_kind("", states, cancelled=True, default="approved"), "cancelled")
        self.assertEqual(status_kind("", [], approval=False, default="approved"), "requested")
        self.assertEqual(status_kind("", [], lottery=True, default="approved"), "won")
        self.assertEqual(status_kind("체크아웃", [], default="approved"), "completed")
        self.assertEqual(status_kind("", [], default="completed"), "completed")

    def test_time_model_follows_the_roles(self):
        self.assertEqual(time_model({"start": [5], "end": [6]}), "range")
        self.assertEqual(time_model({"date": [1], "time_slot": [2]}), "date_slot")
        self.assertEqual(time_model({"date": [1]}), "date")
        self.assertEqual(time_model({}), "none")


class DerivationTests(SimpleTestCase):
    def test_booking_records_configuration_and_dashboard(self):
        report = analyze(BOOKINGS)
        understanding, _ = validate_understanding(model_answer(), report)
        config = derive_service(understanding, report)
        self.assertEqual(config["resources"]["levels"], ["기관명", "상품명"])
        booking = config["booking"]
        self.assertTrue(booking["acceptsNew"] and booking["approvalRequired"])
        self.assertEqual((booking["timeModel"], booking["dateColumn"], booking["bookerColumn"], booking["partySizeColumns"]),
                         ("date", 4, 5, [6]))
        view = config["dashboard"]["preview"]["views"][0]
        self.assertEqual(view["template"], "table")
        self.assertEqual(view["charts"][0], {"type": "donut", "groupColumn": 7, "aggregate": "count"})
        self.assertIn({"type": "bar", "groupColumn": 2, "aggregate": "count"}, view["charts"])
        self.assertEqual([persona["id"] for persona in config["personas"]], ["booker", "admin", "org_manager"])

    def test_sheets_without_resources_lose_the_booking_features(self):
        report = analyze(BOOKINGS)
        understanding, _ = validate_understanding(model_answer(sheetKind="aggregate", resourceColumns=[]), report)
        config = derive_service(understanding, report)
        self.assertFalse(config["booking"]["acceptsNew"])
        for persona in config["personas"]:
            self.assertNotIn("make_reservation", persona["features"])
            self.assertNotIn("review_reservations", persona["features"])
        self.assertTrue(config["notes"])


class MaterializeMixin:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)

    def upload(self, data, answer):
        report = analyze(data)
        upload = Upload(session_key="test", original_name="sheet.csv", file_type="csv", size=len(data),
                        encoding=report["source"]["encoding"], analysis=report)
        upload.original.save("sheet.csv", ContentFile(data), save=False)
        upload.save()
        upload.understanding, _ = validate_understanding(answer, report)
        upload.save(update_fields=["understanding"])
        return upload


@override_settings(ANTHROPIC_API_KEY="")
class MaterializationTests(MaterializeMixin, TestCase):
    def test_booking_records_become_a_resource_tree_and_bookings(self):
        upload = self.upload(BOOKINGS, model_answer())
        config, counts = build_service(upload)
        self.assertEqual(counts, {"resources": 6, "bookings": 10})
        tops = Resource.objects.filter(upload=upload, level=0).order_by("name")
        self.assertEqual([r.name for r in tops], ["변산 자연휴양림", "유명산 자연휴양림"])
        rooms = Resource.objects.filter(upload=upload, level=1, parent=tops[0]).order_by("name")
        self.assertEqual([r.name for r in rooms], ["바다향기5", "우럭"])
        self.assertEqual(Resource.objects.get(upload=upload, path="변산 자연휴양림 / 우럭").level, 1)
        statuses = dict(Booking.objects.filter(upload=upload).values_list("status").annotate(n=__import__("django.db.models", fromlist=["Count"]).Count("id")))
        self.assertEqual(statuses, {"requested": 2, "approved": 4, "completed": 2, "cancelled": 2})
        first = Booking.objects.get(upload=upload, source_row__row_number=2)
        self.assertEqual((first.booker, first.party_size, first.date, first.payment, first.status_label),
                         ("김**", 4, date(2026, 3, 3), "Y", "체크아웃"))
        self.assertEqual(first.resource.path, "변산 자연휴양림 / 우럭")
        # repeatable: a second build replaces instead of duplicating
        build_service(upload)
        self.assertEqual(Booking.objects.filter(upload=upload).count(), 10)
        self.assertEqual(Resource.objects.filter(upload=upload).count(), 6)

    def test_catalog_rows_become_resources_with_attributes_and_capacity(self):
        upload = self.upload(CATALOG, catalog_answer())
        config, counts = build_service(upload)
        self.assertEqual(counts, {"resources": 8})  # 3 zones + 5 facilities
        self.assertEqual(Booking.objects.filter(upload=upload).count(), 0)
        igloo = Resource.objects.get(upload=upload, name="이글루A")
        self.assertEqual((igloo.level, igloo.parent.name, igloo.capacity), (1, "A구역", 5))
        self.assertEqual(igloo.attributes["평일금액"], "50000")
        self.assertEqual(igloo.attributes["이용시작시간"], "14:00")
        self.assertNotIn("데이터기준일자", igloo.attributes)
        self.assertTrue(config["booking"]["acceptsNew"])
        self.assertFalse(config["booking"]["approvalRequired"])

    def test_wide_sheets_unpivot_into_one_resource_per_column(self):
        upload = self.upload(WIDE, wide_answer())
        config, counts = build_service(upload)
        self.assertEqual(config["resources"]["widePairs"], [[2, 3], [4, 5]])
        self.assertEqual(counts, {"resources": 2, "bookings": 6})
        hall = Resource.objects.get(upload=upload, name="대공연장")
        booked = Booking.objects.filter(upload=upload, resource=hall).order_by("date")
        self.assertEqual([b.purpose for b in booked], ["의정보고회", "어린이집발표회", "합창단 정기연주회", "무용발표회"])
        self.assertEqual((booked[0].time_slot, timezone.localtime(booked[0].starts_at).hour, timezone.localtime(booked[0].ends_at).hour), ("10:00~12:00", 10, 12))
        self.assertEqual(Booking.objects.filter(upload=upload, resource__name="소공연장").count(), 2)

    def test_schedule_rows_become_slots_with_attendance(self):
        upload = self.upload(SLOTS, slots_answer())
        config, counts = build_service(upload)
        self.assertEqual(config["booking"]["timeModel"], "date_slot")
        self.assertEqual(counts, {"resources": 3, "slots": 6})
        slot = Slot.objects.get(upload=upload, date=date(2026, 4, 16))
        self.assertEqual((slot.resource.name, slot.time_slot, slot.imported_count), ("선암호수공원", "오전10시~12시", 17))
        self.assertEqual((timezone.localtime(slot.starts_at).hour, timezone.localtime(slot.ends_at).hour), (10, 12))
        afternoon = Slot.objects.get(upload=upload, date=date(2026, 4, 20))
        self.assertEqual((timezone.localtime(afternoon.starts_at).hour, timezone.localtime(afternoon.ends_at).hour), (14, 16))


SINGLE_STAGE = ("예약일,시작시간,종료시간,내용\n"
                "2025-11-15,13:00,14:00,버스킹 공연\n"
                "2025-11-15,15:00,16:00,주말이용불가\n"
                "2025-11-22,13:00,14:00,댄스 동아리\n"
                "2025-11-29,15:00,16:00,어린이 합창\n"
                "2025-12-06,13:00,14:00,데크 작업\n").encode("utf-8")

PERIOD_SLOTS = ("시설,시작월일,종료월일,시작시간,종료시간\n"
                "울산대종 타종1회차,2024-01-01,2024-12-31,12:00,13:00\n"
                "울산대종 타종2회차,2024-01-01,2024-12-31,15:00,16:00\n"
                "전망대,2024-03-01,2024-11-30,09:00,18:00\n"
                "전망대 야간,2024-06-01,2024-08-31,19:00,22:00\n"
                "체험관,2024-01-01,2024-12-31,10:00,17:00\n").encode("utf-8")


def single_stage_answer():
    return model_answer(sheetKind="booking_records", subject="공연 데크", resourceColumns=[],
                        columnRoles=["date", "start", "end", "purpose"], columnEvidence=[""] * 4,
                        booking={"mode": "record_only", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[], questions=[])


def period_slots_answer():
    return model_answer(sheetKind="schedule_slots", subject="공공시설 이용 시간대", resourceColumns=[1],
                        columnRoles=["resource", "start", "end", "start", "end"], columnEvidence=[""] * 5,
                        booking={"mode": "instant", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[], questions=[])


@override_settings(ANTHROPIC_API_KEY="")
class SingleResourceTests(MaterializeMixin, TestCase):
    def test_a_sheet_about_one_thing_gets_an_implicit_resource_and_still_takes_bookings(self):
        upload = self.upload(SINGLE_STAGE, single_stage_answer())
        config, counts = build_service(upload)
        self.assertTrue(config["resources"]["implicit"])
        self.assertEqual(config["resources"]["levels"], ["공연 데크"])
        self.assertTrue(config["booking"]["acceptsNew"])
        self.assertFalse(config["booking"]["approvalRequired"])
        booker = next(persona for persona in config["personas"] if persona["id"] == "booker")
        self.assertIn("make_reservation", booker["features"])
        self.assertEqual(counts, {"resources": 1, "bookings": 5})
        stage = Resource.objects.get(upload=upload)
        self.assertEqual((stage.name, stage.level), ("공연 데크", 0))
        first = Booking.objects.filter(upload=upload).order_by("date", "starts_at").first()
        self.assertEqual((first.resource_id, first.status, first.purpose), (stage.id, "completed", "버스킹 공연"))
        self.assertEqual(timezone.localtime(first.starts_at).hour, 13)

    def test_a_date_column_and_a_time_column_both_marked_start_combine(self):
        upload = self.upload(PERIOD_SLOTS, period_slots_answer())
        config, counts = build_service(upload)
        self.assertEqual(config["booking"]["startColumns"], [2, 4])
        self.assertEqual(counts, {"resources": 5, "slots": 5})
        bell = Slot.objects.get(upload=upload, resource__name="울산대종 타종1회차")
        self.assertEqual((bell.date, timezone.localtime(bell.starts_at).hour, timezone.localtime(bell.ends_at).hour),
                         (date(2024, 1, 1), 12, 13))


CODED = ("예약신청번호,시설코드,예약시작일,예약종료일,승인여부,결제여부,금액\n"
         "1,pt_room,2026-06-26,2026-06-30,Y,N,0\n"
         "2,edu_center,2026-06-01,2026-06-01,Y,Y,325710\n"
         "3,pt_room,2026-07-02,2026-07-02,N,N,0\n"
         "4,medium_room,2026-07-05,2026-07-05,Y,N,120000\n"
         "5,edu_center,2026-07-10,2026-07-11,Y,Y,200000\n").encode("utf-8")


def coded_answer():
    return model_answer(sheetKind="booking_records", subject="회의실·교육시설", resourceColumns=[2],
                        columnRoles=["identifier", "resource", "start", "end", "approval", "payment", "amount"], columnEvidence=[""] * 7,
                        booking={"mode": "approval", "statusColumn": 0, "stateValues": [], "stateKinds": [], "evidence": ""},
                        personas=[{"id": "finance", "title": "결제 담당자", "scopeColumn": 0, "features": ["review_reservations"], "evidence": ""}],
                        valueLabels=[{"column": 2, "value": "pt_room", "label": "PT실(추정)"}, {"column": 2, "value": "edu_center", "label": "교육센터"},
                                     {"column": 2, "value": "nowhere", "label": "없는 값"}, {"column": 5, "value": "Y", "label": "승인"}],
                        questions=[])


@override_settings(ANTHROPIC_API_KEY="")
class CodeLabelTests(MaterializeMixin, TestCase):
    def test_code_values_get_display_names_and_keep_the_code(self):
        upload = self.upload(CODED, coded_answer())
        config, counts = build_service(upload)
        self.assertEqual([(item["value"], item["label"]) for item in config["valueLabels"]],
                         [("pt_room", "PT실(추정)"), ("edu_center", "교육센터")])  # column 5 is not a resource or status column
        self.assertEqual(counts, {"resources": 3, "bookings": 5})
        pt = Resource.objects.get(upload=upload, name="PT실(추정)")
        self.assertEqual(pt.attributes["원본 코드"], "pt_room")
        self.assertEqual(pt.attributes["기록 건수"], "2건")  # records summarized onto the resource
        self.assertEqual(config["booking"]["unit"], "period")  # 예약시작일~종료일 on a meeting room
        self.assertEqual(Booking.objects.filter(upload=upload, resource=pt).count(), 2)
        self.assertNotIn("원본 코드", Resource.objects.get(upload=upload, name="medium_room").attributes)
        finance = next(p for p in config["personas"] if p["id"] == "finance")
        self.assertEqual(finance["features"], ["manage_payments"])  # review_reservations is not a finance feature
