"""Offline checks for CSV-specific v2 request construction."""

import json
import re
from unittest import TestCase

from .analysis import analyze
from .preview_request_v2 import PreviewRequestError, build_input, build_prompt, build_schema


class PreviewRequestV2Tests(TestCase):
    def test_samples_span_full_csv_and_content_matches_schema_numbers(self):
        rows = "\n".join(f"Place {index},category {index % 3},https://example.org/{index}.jpg"
                         for index in range(1, 41))
        report = analyze(("name,category,image\n" + rows + "\n").encode())
        self.assertEqual(len(report["preview"]), 20)
        selected = [row["row_number"] - 2 for row in report["inference_samples"]]
        self.assertEqual(len(selected), 10)
        self.assertEqual(len(set(selected)), 10)
        self.assertTrue({0, 1, 19, 20, 38, 39} <= set(selected))
        remaining = [index for index in range(40) if index not in {0, 1, 19, 20, 38, 39}]
        for part in range(4):
            segment = set(remaining[part * len(remaining) // 4:(part + 1) * len(remaining) // 4])
            self.assertEqual(len(segment.intersection(selected)), 1)
        self.assertEqual(report["inference_samples"], analyze(("name,category,image\n" + rows + "\n").encode())["inference_samples"])
        content = build_input(report)
        self.assertEqual(content["sample_rows"][-1]["values"][0], "Place 40")
        self.assertEqual([column["number"] for column in content["columns"]], [1, 2, 3])
        prompt = build_prompt(report)
        payload = re.search(r"<csv_analysis>\s*(.*?)\s*</csv_analysis>",
                            prompt["messages"][0]["content"], re.DOTALL)
        self.assertIsNotNone(payload)
        self.assertEqual(json.loads(payload.group(1)), content)
        self.assertNotIn("{{", prompt["messages"][0]["content"])
        self.assertEqual(prompt["output_config"]["format"]["schema"]["$defs"]["allColumns"]["enum"],
                         [1, 2, 3])

    def test_unusable_optional_roles_and_group_template_are_absent(self):
        report = analyze(b"identifier,value\na,1\nb,2\nc,3\n")
        schema = build_schema(report)
        self.assertNotIn("groupColumn", schema["$defs"])
        self.assertNotIn("imageColumn", schema["$defs"])
        self.assertNotIn("charts", schema["$defs"])
        views = schema["properties"]["views"]["items"]["anyOf"]
        self.assertEqual([view["properties"]["template"]["enum"][0] for view in views],
                         ["cards", "table"])
        self.assertNotIn("badgeColumn", views[0]["properties"])

    def test_duplicate_headers_keep_distinct_numbers_and_values_are_clipped(self):
        long_value = "x" * 200
        report = analyze(("name,name\n" + long_value + ",short\n").encode())
        content = build_input(report)
        self.assertEqual(len(content["sample_rows"][0]["values"][0]), 160)
        self.assertEqual(content["columns"][0]["name"], content["columns"][1]["name"])
        self.assertEqual(content["columns"][0]["number"], 1)
        self.assertEqual(content["columns"][1]["number"], 2)
        self.assertIn("sample_rows.2.1", content["sampling"]["truncated_paths"])

    def test_header_only_has_no_empty_enums_and_old_reports_need_reanalysis(self):
        report = analyze(b"name,category\n")
        schema = build_schema(report)
        self.assertEqual(schema["$defs"]["titleColumn"]["enum"], [1, 2])
        self.assertFalse(any(definition.get("enum") == [] for definition in schema["$defs"].values()))
        self.assertEqual(build_input(report)["sample_rows"], [])
        del report["inference_samples"]
        with self.assertRaises(PreviewRequestError):
            build_input(report)

    def test_short_csv_sends_each_data_row_once(self):
        report = analyze(b"name\na\nb\nc\nd\ne\nf\ng\n")
        self.assertEqual([row["row_number"] for row in report["inference_samples"]],
                         [2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(build_input(report)["sampling"]["max_rows"], 10)
