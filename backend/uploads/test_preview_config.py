"""Synthetic Preview config fixtures only; no browser, database, or API keys."""
import copy
import unittest

from .preview_config import PreviewConfigError, TEMPLATE_CATALOG, normalize_preview_config, validate_preview_config


class PreviewConfigTests(unittest.TestCase):
    def setUp(self):
        self.columns = [
            {"id": "column_1", "name": "서비스명"},
            {"id": "column_2", "name": "서비스상태"},
            {"id": "column_3", "name": "소분류명"},
            {"id": "column_4", "name": "바로가기URL"},
        ]
        self.config = {
            "version": 1,
            "title": "서비스 미리보기",
            "pages": [
                {
                    "id": "services",
                    "template": "cards",
                    "title": "서비스 목록",
                    "detailPage": "service_detail",
                    "bindings": {
                        "title": "column_1",
                        "badge": "column_2",
                        "fields": ["column_3"],
                    },
                    "charts": [
                        {"type": "bar", "title": "분류별 수", "groupBy": "column_3", "aggregate": "count"},
                    ],
                },
                {
                    "id": "table",
                    "template": "table",
                    "title": "표",
                    "bindings": {"fields": ["column_1", "column_2", "column_4"]},
                },
                {
                    "id": "groups",
                    "template": "grouped",
                    "title": "분류별 서비스",
                    "detailPage": "service_detail",
                    "bindings": {
                        "group": "column_3",
                        "title": "column_1",
                        "badge": "column_2",
                        "fields": ["column_2"],
                    },
                },
                {
                    "id": "service_detail",
                    "template": "detail",
                    "title": "상세",
                    "bindings": {"title": "column_1", "link": "column_4", "fields": ["column_2", "column_3"]},
                },
            ],
        }

    def test_ready_catalog_matches_preview_scope(self):
        self.assertEqual(set(TEMPLATE_CATALOG), {"cards", "detail", "table", "map", "calendar", "grouped", "form"})
        self.assertEqual({key for key, value in TEMPLATE_CATALOG.items() if value["ready"]},
                         {"cards", "detail", "table", "grouped"})

    def test_normalize_removes_provider_noise_before_strict_validation(self):
        value = copy.deepcopy(self.config)
        value['pages'][0]['bindings']['link'] = 'column_4'
        value['pages'][2]['bindings']['group'] = 'column_3,'
        value['pages'][2]['bindings']['phone'] = 'column_4'
        normalized = normalize_preview_config(value, self.columns)
        self.assertNotIn('link', normalized['pages'][0]['bindings'])
        self.assertNotIn('phone', normalized['pages'][2]['bindings'])
        self.assertEqual(normalized['pages'][2]['bindings']['group'], 'column_3')
        self.assertIs(validate_preview_config(normalized, self.columns), normalized)

    def test_normalize_drops_unreferenced_incomplete_placeholder_pages(self):
        value = copy.deepcopy(self.config)
        value['pages'].append({
            'id': 'placeholder',
            'template': 'detail',
            'title': 'placeholder',
            'bindings': {},
        })
        normalized = normalize_preview_config(value, self.columns)
        self.assertNotIn('placeholder', [page['id'] for page in normalized['pages']])
        self.assertIs(validate_preview_config(normalized, self.columns), normalized)

    def test_normalize_keeps_referenced_incomplete_pages_for_strict_rejection(self):
        value = copy.deepcopy(self.config)
        value['pages'][0]['detailPage'] = 'broken_detail'
        value['pages'].append({
            'id': 'broken_detail',
            'template': 'detail',
            'title': 'Broken detail',
            'bindings': {},
        })
        normalized = normalize_preview_config(value, self.columns)
        self.assertIn('broken_detail', [page['id'] for page in normalized['pages']])
        with self.assertRaises(PreviewConfigError):
            validate_preview_config(normalized, self.columns)

    def test_valid_config_returns_original_object(self):
        before = copy.deepcopy(self.config)
        self.assertIs(validate_preview_config(self.config, self.columns), self.config)
        self.assertEqual(self.config, before)

    def test_reject_unready_template_by_default(self):
        value = copy.deepcopy(self.config)
        value["pages"][1]["template"] = "map"
        value["pages"][1]["bindings"] = {"title": "column_1", "latitude": "column_2", "longitude": "column_3"}
        with self.assertRaises(PreviewConfigError):
            validate_preview_config(value, self.columns)
        self.assertIs(validate_preview_config(value, self.columns, require_ready=False), value)

    def test_reject_bad_structure_and_column_references(self):
        mutations = [
            lambda c: c.update(version=True),
            lambda c: c.update(extra="code"),
            lambda c: c.update(pages=[]),
            lambda c: c["pages"][0].update(id="Services"),
            lambda c: c["pages"][1].update(id="services"),
            lambda c: c["pages"][0].update(template="custom_code"),
            lambda c: c["pages"][0]["bindings"].update(title="column_99"),
            lambda c: c["pages"][0]["bindings"].update(fields=["column_3", "column_3"]),
            lambda c: c["pages"][1]["bindings"].update(fields=[]),
            lambda c: c["pages"][0].update(script="alert(1)"),
            lambda c: c["pages"][0]["bindings"].update(html="column_1"),
            lambda c: c["pages"][1].update(detailPage="service_detail"),
            lambda c: c["pages"][0].update(detailPage="missing"),
            lambda c: c["pages"][0]["charts"][0].update(type="line"),
            lambda c: c["pages"][0]["charts"][0].update(groupBy="column_99"),
            lambda c: c["pages"][3].update(charts=[]),
        ]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(self.config)
            mutate(value)
            with self.subTest(index=index), self.assertRaises(PreviewConfigError):
                validate_preview_config(value, self.columns)


if __name__ == "__main__":
    unittest.main()
