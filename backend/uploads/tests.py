import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from .analysis import TableError, analyze
from .models import Upload


class AnalysisTests(SimpleTestCase):
    def test_korean_encodings_and_original_strings(self):
        text = '서비스ID,전화번호,좌표,시작일,상세정보\r\n001,02-123-4567,127.02,2026-09-14,"안내, 첫 줄\n둘째 줄"\r\n'
        for encoding in ("utf-8-sig", "euc-kr", "cp949"):
            with self.subTest(encoding=encoding):
                report = analyze(text.encode(encoding), encoding)
                self.assertEqual(report["row_count"], 1)
                self.assertEqual(report["preview"][0]["values"][0], "001")
                self.assertEqual(report["preview"][0]["values"][4], "안내, 첫 줄\n둘째 줄")
                self.assertEqual(report["columns"][0]["candidate"], "text")
                self.assertEqual(report["columns"][1]["candidate"], "text")
                self.assertEqual(report["columns"][2]["number_ratio"], 1)
                self.assertEqual(report["columns"][3]["date_ratio"], 1)

    def test_messy_headers_missing_mixed_and_ragged_rows(self):
        report = analyze(b'name,name,,value\na,a, ,1\nb,a,x,no,extra\n,,,,\nc\n')
        self.assertEqual(report["column_count"], 5)
        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["skipped_blank_rows"], 1)
        self.assertEqual(report["columns"][1]["unique_count"], 1)
        self.assertEqual(report["columns"][3]["candidate"], "mixed")
        self.assertEqual(report["columns"][3]["missing_count"], 1)
        self.assertTrue(report["columns"][0]["issues"])
        self.assertTrue(report["columns"][2]["issues"])
        self.assertEqual(report["preview"][-1]["row_number"], 5)

    def test_preview_limit_and_empty_column_preservation(self):
        report = analyze(('a,\n' + '1,\n' * 25).encode())
        self.assertEqual(report["row_count"], 25)
        self.assertEqual(len(report["preview"]), 20)
        self.assertEqual(report["column_count"], 2)
        self.assertEqual(len(report["inference_samples"]), 10)

    def test_header_only_and_formula(self):
        self.assertEqual(analyze(b'name\n')["row_count"], 0)
        report = analyze(b'value\n=1+2\n')
        self.assertEqual(report["preview"][0]["values"], ["=1+2"])
        self.assertEqual(report["columns"][0]["candidate"], "formula")

    def test_reject_invalid_input(self):
        for data in (b'', b'\n', b'a\n"unterminated', b'a\n\x00', b'a\n\xff'):
            with self.subTest(data=data), self.assertRaises(TableError):
                analyze(data)
        with self.assertRaises(TableError):
            analyze(b'a\n1', 'invalid')

    def test_limits(self):
        with self.assertRaises(TableError):
            analyze((','.join(['a'] * 201)).encode())
        with self.assertRaises(TableError):
            analyze(('a\n' + '1\n' * 50_001).encode())

    def test_invalid_byte_replacement_requires_opt_in(self):
        data = '이름\n안내'.encode('cp949') + b'\x82 \n'
        with self.assertRaises(TableError):
            analyze(data, 'cp949')
        with self.assertRaises(TableError):
            analyze(data, 'auto', True)
        report = analyze(data, 'cp949', True)
        self.assertEqual(report['source']['replaced_bytes'], 1)
        self.assertEqual(report['preview'][0]['values'], ['안내� '])
        self.assertTrue(report['warnings'])

    def test_auto_recovers_sparse_invalid_bytes_with_warning(self):
        for encoding in ('cp949', 'utf-8-sig'):
            with self.subTest(encoding=encoding):
                data = ('이름\n' + '정상한글' * 500).encode(encoding) + b'\xff\n'
                report = analyze(data)
                self.assertEqual(report['source']['encoding'], encoding)
                self.assertEqual(report['source']['replaced_bytes'], 1)
                self.assertTrue(report['preview'][0]['values'][0].endswith('�'))
                self.assertTrue(report['warnings'])
        # ASCII content must not conceal a badly decoded non-ASCII segment.
        with self.assertRaises(TableError):
            analyze(b'name\n' + b'a' * 5000 + b'\xff\n')


class UploadAPITests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(MEDIA_ROOT=temporary.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get('/api/session/').json()['csrf_token']

    def post_file(self, data=b'id,name\n001,test\n', name='sample.csv', **kwargs):
        return self.client.post('/api/uploads/', {'file': SimpleUploadedFile(name, data), **kwargs},
                                format='multipart', HTTP_X_CSRFTOKEN=self.token)

    def test_upload_persist_retrieve_download_and_session_isolation(self):
        original = '이름,설명\r\n테스트,"긴 설명, 쉼표"\r\n'.encode('cp949')
        response = self.post_file(original)
        self.assertEqual(response.status_code, 201, response.content)
        upload = Upload.objects.get()
        self.assertEqual(upload.encoding, 'cp949')
        with upload.original.open('rb') as stored:
            self.assertEqual(stored.read(), original)
        url = f'/api/uploads/{upload.pk}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        download = self.client.get(url + 'original/')
        self.assertEqual(b''.join(download.streaming_content), original)
        other = APIClient()
        self.assertEqual(other.get(url).status_code, 404)
        self.assertEqual(other.get(url + 'original/').status_code, 404)

    def test_rows_endpoint_pages_all_nonblank_records_in_analysis_order(self):
        lines = ['name,value'] + [f'item-{index},{index}' for index in range(1, 11)]
        lines += [''] + [f'item-{index},{index}' for index in range(11, 46)]
        upload = self.post_file(('\n'.join(lines) + '\n').encode()).data
        self.assertEqual(upload['analysis']['row_count'], 45)
        url = f"/api/uploads/{upload['id']}/rows/"
        first = self.client.get(url).data
        second = self.client.get(url + '?page=2').data
        third = self.client.get(url + '?page=3').data
        self.assertEqual(first['rows'], upload['analysis']['preview'])
        self.assertEqual((len(first['rows']), len(second['rows']), len(third['rows'])), (20, 20, 5))
        self.assertEqual(second['rows'][0]['row_number'], 23)
        self.assertEqual(third['rows'][-1]['values'][0], 'item-45')
        self.assertFalse(third['has_next'])
        self.assertEqual(self.client.get(url + '?page=4').status_code, 400)
        self.assertEqual(APIClient().get(url).status_code, 404)

    def test_chart_counts_cover_all_rows_and_respect_session(self):
        lines = ['name,category'] + [f'item-{index},{"A" if index <= 20 else "B"}'
                                    for index in range(1, 46)] + ['item-46,', 'item-47,   ']
        upload = self.post_file(('\n'.join(lines) + '\n').encode()).data
        url = f"/api/uploads/{upload['id']}/chart-counts/?columns=2"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['row_count'], 47)
        summary = response.data['columns']['column_2']
        self.assertEqual(summary['total'], 47)
        self.assertEqual([(item['label'], item['count']) for item in summary['groups']],
                         [('B', 25), ('A', 20), ('값 없음', 2)])
        self.assertEqual(sum(item['count'] for item in summary['groups']), 47)
        self.assertEqual(self.client.get(url + ',3').status_code, 400)
        self.assertEqual(APIClient().get(url).status_code, 404)

    def test_csrf_required_and_invalid_upload_not_saved(self):
        response = self.client.post('/api/uploads/', {'file': SimpleUploadedFile('x.csv', b'a\n1')}, format='multipart')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.post_file(name='sample.xlsx').status_code, 400)
        self.assertEqual(self.post_file(data=b'').status_code, 400)
        self.assertEqual(Upload.objects.count(), 0)

    def test_failed_reanalysis_keeps_existing_result(self):
        response = self.post_file('이름\n테스트\n'.encode('cp949'))
        self.assertEqual(response.status_code, 201)
        upload = Upload.objects.get()
        before = upload.analysis
        response = self.client.post(f'/api/uploads/{upload.pk}/', {'encoding': 'utf-8-sig'},
                                    format='json', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code, 400)
        upload.refresh_from_db()
        self.assertEqual(upload.analysis, before)
