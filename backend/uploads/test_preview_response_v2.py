"""Meaningful offline checks for Preview v2 response safety."""

import json
from unittest import TestCase

from .analysis import analyze
from .preview_response_v2 import prepare_preview_response


class PreviewResponseV2Tests(TestCase):
    def setUp(self):
        self.report = analyze(b"name,kind,detail\nA,park,one\nB,room,two\nC,park,three\nD,room,four\n")

    def prepare(self, value):
        return prepare_preview_response(json.dumps(value), self.report)

    def test_deduplicates_preserving_order_and_removes_repeated_display_fields(self):
        cards = {"template": "cards", "titleColumn": 1, "subtitleColumn": 3,
                 "badgeColumn": 2, "fields": [3, 1, 2, 3],
                 "charts": [{"type": "bar", "groupColumn": 2, "aggregate": "count"},
                            {"type": "bar", "groupColumn": 2, "aggregate": "count"}]}
        table = {"template": "table", "columns": [3, 1, 3, 2]}
        outcome = self.prepare({"version": 2, "views": [cards, cards, table]})
        self.assertFalse(outcome["used_fallback"])
        self.assertEqual(len(outcome["preview"]["views"]), 2)
        self.assertEqual(outcome["preview"]["views"][0]["fields"], [])
        self.assertEqual(len(outcome["preview"]["views"][0]["charts"]), 1)
        self.assertEqual(outcome["preview"]["views"][1]["columns"], [3, 1, 2])

    def test_invalid_column_candidate_and_extra_key_use_full_column_fallback(self):
        for view in (
            {"template": "grouped", "groupColumn": 1, "titleColumn": 1, "fields": []},
            {"template": "table", "columns": [1, 99]},
            {"template": "table", "columns": [1], "title": "injected"},
            {"template": "table", "columns": [True]},
        ):
            with self.subTest(view=view):
                outcome = self.prepare({"version": 2, "views": [view]})
                self.assertTrue(outcome["used_fallback"])
                self.assertEqual(outcome["preview"]["views"],
                                 [{"template": "table", "columns": [1, 2, 3]}])
                self.assertTrue(outcome["validation_error"])

    def test_malformed_or_duplicate_json_key_uses_fallback(self):
        for raw in ('```json\n{"version":2}\n```',
                    '{"version":2,"version":2,"views":[]}',
                    '{"version":2,"views":[]}'):
            with self.subTest(raw=raw):
                self.assertTrue(prepare_preview_response(raw, self.report)["used_fallback"])

    def test_caps_views_and_charts_after_validation(self):
        charts = [{"type": kind, "groupColumn": 2, "aggregate": "count"}
                  for kind in ("bar", "donut", "bar", "donut", "bar")]
        views = [{"template": "cards", "titleColumn": 1, "fields": [3], "charts": charts}]
        views += [{"template": "table", "columns": columns} for columns in
                  ([1], [2], [3], [1, 2], [2, 1], [1, 3], [3, 1])]
        outcome = self.prepare({"version": 2, "views": views})
        self.assertFalse(outcome["used_fallback"])
        self.assertEqual(len(outcome["preview"]["views"]), 7)
        self.assertEqual(len(outcome["preview"]["views"][0]["charts"]), 2)
