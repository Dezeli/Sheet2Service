import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Upload, ManagedRow, FieldChoice


class FieldLabelTests(APITestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get('/api/session/').data['csrf_token']
        response = self.client.post('/api/uploads/', {'file': SimpleUploadedFile('items.csv', b'name,kind\nA,park\nB,room\n')},
                                    format='multipart', HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code, 201)
        self.base = f"/api/uploads/{response.data['id']}/"
        self.upload = Upload.objects.get(pk=response.data['id'])

    def patch(self, number, body):
        return self.client.patch(f'{self.base}fields/{number}/', body, format='json', HTTP_X_CSRFTOKEN=self.token)

    def test_alias_persists_without_changing_original_or_field_connections(self):
        before = self.upload.analysis
        rows = list(ManagedRow.objects.filter(upload=self.upload).values_list('id', 'values'))
        choices = list(FieldChoice.objects.filter(upload=self.upload).values_list('id', 'column_number', 'value'))
        response = self.patch(1, {'label': ' Item title '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['field_labels'], {'1': 'Item title'})
        self.assertEqual(self.client.get(self.base).data['field_labels'], {'1': 'Item title'})
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.analysis, before)
        self.assertEqual(list(ManagedRow.objects.filter(upload=self.upload).values_list('id', 'values')), rows)
        self.assertEqual(list(FieldChoice.objects.filter(upload=self.upload).values_list('id', 'column_number', 'value')), choices)
        self.assertEqual(self.patch(2, {'label': 'Category'}).data['field_labels'], {'1': 'Item title', '2': 'Category'})
        self.assertEqual(self.patch(1, {'label': 'name'}).data['field_labels'], {'2': 'Category'})

    def test_rejects_invalid_labels_and_columns(self):
        for body in ({'label': ''}, {'label': ' '}, {'label': None}, {'label': True}, {'label': 'a' * 121}, {'label': 'a\nb'}, {'label': 'x', 'extra': 1}, []):
            self.assertEqual(self.patch(1, body).status_code, 400)
        self.assertEqual(self.patch(0, {'label': 'x'}).status_code, 400)
        self.assertEqual(self.patch(3, {'label': 'x'}).status_code, 400)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.field_labels, {})

    def test_requires_ownership_and_csrf(self):
        other = APIClient(enforce_csrf_checks=True)
        token = other.get('/api/session/').data['csrf_token']
        self.assertEqual(other.patch(self.base + 'fields/1/', {'label': 'x'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 404)
        self.assertEqual(self.client.patch(self.base + 'fields/1/', {'label': 'x'}, format='json').status_code, 403)
