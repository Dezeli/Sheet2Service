"""Analyze a local CSV and, only with --approve, run the one reservation-understanding call.

Without --approve the command prints the approval summary (purpose, model, data scope, fingerprint)
and the operational signals, and makes no network call.
"""
import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from uploads.analysis import TableError, analyze
from uploads.managed import ensure_imported
from uploads.models import Upload
from uploads.reservation_understanding import summary_lines
from uploads.reservation_understanding_request import (run_understanding, understanding_approval_summary,
                                                       understanding_request_body)


class Command(BaseCommand):
    help = "로컬 CSV를 분석하고, --approve 문구가 있을 때만 예약 시트 이해 호출을 1회 실행합니다."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--approve", help="호출 승인 기록 문구. 없으면 호출하지 않습니다.")
        parser.add_argument("--json", action="store_true", help="이해 결과를 JSON으로 출력")
        parser.add_argument("--keep", action="store_true", help="업로드 레코드를 삭제하지 않고 남김")
        parser.add_argument("--name", help="프롬프트에 보낼 파일 이름(기본은 경로의 파일 이름)")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError("CSV 파일을 찾을 수 없습니다.")
        data = path.read_bytes()
        try:
            report = analyze(data)
        except TableError as exc:
            raise CommandError(str(exc)) from exc
        shown = options["name"] or path.name
        upload = Upload(session_key="cli", original_name=shown, file_type="csv", size=len(data),
                        encoding=report["source"]["encoding"], analysis=report)
        upload.original.save(path.name, ContentFile(data, name=path.name), save=False)
        upload.save()
        body = understanding_request_body(report, file_name=shown)
        summary = understanding_approval_summary(body)
        self.stdout.write(f'{shown}: {report["row_count"]}행 {report["column_count"]}열, '
                          f'요청 {len(json.dumps(body, ensure_ascii=False).encode("utf-8")):,}바이트')
        if not options["approve"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            self.stdout.write(json.dumps(report.get("signals"), ensure_ascii=False, indent=1)[:4000])
            if not options["keep"]:
                upload.delete()
            return
        try:
            call, understanding, notes = run_understanding(upload, approval_note=options["approve"],
                                                           approved_at=timezone.now())
        except Exception as exc:  # the ModelCall row keeps the failure; surface it plainly
            raise CommandError(f"호출 실패: {exc}") from exc
        self.stdout.write(f"model_call {call.id} usage {json.dumps(call.usage)}")
        if options["json"]:
            self.stdout.write(json.dumps({"understanding": understanding, "notes": notes}, ensure_ascii=False, indent=1))
        else:
            for line in summary_lines(understanding, report):
                self.stdout.write(line)
            for note in notes:
                self.stdout.write(f"  보정: {note}")
        if options["keep"]:
            ensure_imported(upload)
            self.stdout.write(f"upload {upload.id} 유지")
        else:
            upload.delete()

