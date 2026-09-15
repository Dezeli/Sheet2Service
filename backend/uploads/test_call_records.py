import io
import json

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .call_records import finish_call, start_call
from .models import ModelCall, Upload


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class CallRecordTests(TestCase):
    def start(self, **kwargs):
        return start_call(purpose="합성 추론 테스트", request_body={
            "model": "test-model", "messages": [{"role": "user", "content": "가상 데이터"}],
            "max_tokens": 100,
        }, approval_note="합성 승인 기록", approved_at=timezone.now(), **kwargs)

    def test_request_and_response_survive_reload_and_are_searchable(self):
        record = self.start()
        finish_call(record, status=ModelCall.Status.SUCCEEDED,
                    response_body='{"content":[{"text":"결과"}]}', http_status=200,
                    provider_request_id="synthetic-request", parsed_result={"summary": "결과"},
                    usage={"input_tokens": 10, "output_tokens": 5})
        output = io.StringIO()
        call_command("model_calls", id=str(record.id), stdout=output)
        saved = json.loads(output.getvalue())
        self.assertEqual(saved["request_body"]["messages"][0]["content"], "가상 데이터")
        self.assertEqual(saved["parsed_result"], {"summary": "결과"})
        self.assertEqual(saved["usage"]["input_tokens"], 10)
        self.assertIsNotNone(saved["completed_at"])
        output = io.StringIO()
        call_command("model_calls", model="test-model", purpose="합성", stdout=output)
        self.assertEqual(len(json.loads(output.getvalue())), 1)

    def test_failure_and_unknown_preserve_error_without_retry(self):
        for status in (ModelCall.Status.FAILED, ModelCall.Status.UNKNOWN):
            record = self.start()
            finish_call(record, status=status, response_body="not json", error_type="Timeout",
                        error_message="synthetic error", validation_error="invalid JSON")
            record.refresh_from_db()
            self.assertEqual(record.response_body, "not json")
            self.assertEqual(record.error_type, "Timeout")
            with self.assertRaises(ValueError):
                finish_call(record, status=ModelCall.Status.SUCCEEDED)
        self.assertEqual(ModelCall.objects.count(), 2)

    def test_identical_requests_are_both_saved(self):
        self.assertNotEqual(self.start().pk, self.start().pk)

    def test_secrets_are_redacted(self):
        record = start_call(purpose="test", request_body={"model": "test-model",
                            "x-api-key": "synthetic-test-secret",
                            "messages": [{"content": "synthetic-test-secret"}]},
                            approval_note="approved", approved_at=timezone.now())
        finish_call(record, status=ModelCall.Status.FAILED,
                    response_body='{"authorization":"hidden","error":"synthetic-test-secret"}',
                    error_message="synthetic-test-secret")
        self.assertNotIn("x-api-key", record.request_body)
        self.assertNotIn("synthetic-test-secret", json.dumps(record.request_body))
        self.assertNotIn("authorization", record.response_body)
        self.assertEqual(record.error_message, "[REDACTED]")

    def test_upload_deletion_keeps_record(self):
        upload = Upload.objects.create(session_key="synthetic", original_name="fake.csv",
                                       original="originals/fake/csv", file_type="csv", size=1)
        record = self.start(upload=upload)
        upload.delete()
        record.refresh_from_db()
        self.assertIsNone(record.upload_id)

    def test_approval_required(self):
        with self.assertRaises(ValueError):
            start_call(purpose="test", request_body={"model": "test"},
                       approval_note="", approved_at=None)
        self.assertEqual(ModelCall.objects.count(), 0)
