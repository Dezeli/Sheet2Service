"""Local, read-only lookup of saved requests and results."""
import json
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.dateparse import parse_date

from uploads.models import ModelCall


class Command(BaseCommand):
    help = "저장된 모델 호출 목록 또는 --id로 입력/출력 전체를 조회합니다."

    def add_arguments(self, parser):
        parser.add_argument("--id")
        parser.add_argument("--upload")
        parser.add_argument("--model")
        parser.add_argument("--purpose")
        parser.add_argument("--date", help="호출 날짜 YYYY-MM-DD (프로젝트 시간대)")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        records = ModelCall.objects.all()
        for option, field in (("id", "id"), ("upload", "upload_id")):
            if options[option]:
                try:
                    value = uuid.UUID(options[option])
                except ValueError as exc:
                    raise CommandError("유효한 UUID가 필요합니다.") from exc
                records = records.filter(**{field: value})
        if options["model"]:
            records = records.filter(model=options["model"])
        if options["purpose"]:
            records = records.filter(purpose__icontains=options["purpose"])
        if options["date"]:
            try:
                day = parse_date(options["date"])
            except ValueError:
                day = None
            if day is None:
                raise CommandError("유효한 날짜 YYYY-MM-DD가 필요합니다.")
            records = records.filter(started_at__date=day)
        if not 1 <= options["limit"] <= 100:
            raise CommandError("limit은 1~100이어야 합니다.")
        if options["id"]:
            result = records.values().first()
            if result is None:
                raise CommandError("호출 기록을 찾을 수 없습니다.")
        else:
            result = list(records.values("id", "upload_id", "purpose", "model", "status",
                                         "started_at", "http_status", "usage")[:options["limit"]])
        self.stdout.write(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2))
