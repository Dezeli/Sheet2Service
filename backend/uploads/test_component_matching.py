"""Offline component matching; no Claude request is made."""

from types import SimpleNamespace

from django.test import TestCase

from .component_matching import match_components, record_component_match
from .models import ComponentMatch, ComponentVersion


class ComponentMatchingTests(TestCase):
    def test_reuse_and_composition_are_distinct(self):
        reused = match_components("user", ["catalog.list"])
        self.assertEqual(reused["outcome"], "reuse")
        self.assertEqual(reused["selected_keys"], ["catalog-browser-v1"])
        composed = match_components("user", ["catalog.list", "catalog.search_text"])
        self.assertEqual(composed["outcome"], "compose")
        self.assertEqual(composed["selected_keys"], ["catalog-browser-v1", "text-search-v1"])
        self.assertFalse(composed["missing_capabilities"])

    def test_missing_and_wrong_surface_are_explained(self):
        gap = match_components("user", ["catalog.list", "account.login"])
        self.assertEqual(gap["outcome"], "gap")
        self.assertEqual(gap["selected_keys"], ["catalog-browser-v1"])
        self.assertEqual(gap["missing_capabilities"], ["account.login"])
        wrong_surface = match_components("user", ["catalog.edit_rows"])
        self.assertEqual(wrong_surface["outcome"], "gap")
        self.assertEqual(wrong_surface["candidate_reasons"][0]["reason"], "wrong_surface")

    def test_lineage_prefers_simpler_version_until_it_is_deprecated(self):
        first = ComponentVersion.objects.get(key="catalog-browser-v1")
        later = ComponentVersion.objects.create(key="catalog-browser-v2", family=first.family,
                                                version=2, parent=first, title="목록·상세 개선",
                                                description="같은 기능을 제공하는 후속 버전",
                                                implementation=first.implementation,
                                                capabilities=first.capabilities, surfaces=first.surfaces,
                                                status=ComponentVersion.Status.AVAILABLE)
        self.assertEqual(match_components("user", ["catalog.list"])["selected_keys"], [first.key])
        first.status = ComponentVersion.Status.DEPRECATED
        first.save(update_fields=["status"])
        self.assertEqual(match_components("user", ["catalog.list"])["selected_keys"], [later.key])

    def test_two_versions_of_one_family_cannot_be_combined_as_separate_parts(self):
        def version(key, number, capabilities):
            return SimpleNamespace(key=key, family="map", version=number,
                                   capabilities=capabilities, surfaces=["user"], status="available")
        markers = version("map-v1", 1, ["map.markers"])
        route = version("map-v2", 2, ["map.route"])
        required = ["map.markers", "map.route"]
        self.assertEqual(match_components("user", required, registry=[markers, route])["outcome"], "gap")
        combined = version("map-v3", 3, required)
        self.assertEqual(match_components("user", required, registry=[markers, route, combined])["selected_keys"],
                         ["map-v3"])

    def test_decision_log_contains_capabilities_but_no_request_text(self):
        record, result = record_component_match("user", ["account.login", "catalog.list"])
        self.assertEqual(record.outcome, ComponentMatch.Outcome.GAP)
        self.assertEqual(record.missing_capabilities, ["account.login"])
        self.assertEqual(record.selected_keys, ["catalog-browser-v1"])
        self.assertEqual(record.requested_capabilities, result["requested_capabilities"])

    def test_invalid_request_is_rejected(self):
        for required in ([], ["login"], ["catalog.list", "catalog.list"], ["Catalog.List"]):
            with self.assertRaises(ValueError):
                match_components("user", required)
        with self.assertRaises(ValueError):
            match_components("unknown", ["catalog.list"])
