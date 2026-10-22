"""Registry checks are offline and never call Claude."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from .component_contract import Capability, Implementation, Surface, valid_component_contract
from .models import ComponentVersion


class ComponentRegistryTests(TestCase):
    def test_initial_registry_claims_only_runtime_capabilities(self):
        components = list(ComponentVersion.objects.all())
        self.assertEqual(len(components), 7)
        self.assertTrue(all(item.status == ComponentVersion.Status.AVAILABLE for item in components))
        for item in components:
            item.full_clean()
        self.assertFalse(ComponentVersion.objects.filter(capabilities__contains=["account.login"]).exists())
        self.assertFalse(ComponentVersion.objects.filter(capabilities__contains=["reservation.capacity"]).exists())

    def test_advertised_capability_must_match_approved_implementation(self):
        self.assertTrue(valid_component_contract(Implementation.TEXT_SEARCH,
                                                  [Capability.CATALOG_SEARCH], [Surface.USER]))
        self.assertFalse(valid_component_contract(Implementation.TEXT_SEARCH,
                                                   [Capability.CATALOG_SEARCH, "account.login"], [Surface.USER]))
        self.assertFalse(valid_component_contract(Implementation.TEXT_SEARCH,
                                                   [Capability.CATALOG_SEARCH], [Surface.ADMIN]))

    def test_child_must_follow_same_family_and_higher_version(self):
        parent = ComponentVersion.objects.get(key="text-search-v1")
        child = ComponentVersion(key="text-search-v2", family=parent.family, version=2, parent=parent,
                                 title="텍스트 검색 개선", description="동일 기능 계열의 새 버전",
                                 implementation=parent.implementation,
                                 capabilities=parent.capabilities, surfaces=parent.surfaces)
        child.full_clean()
        child.family = "count-chart"
        with self.assertRaises(ValidationError):
            child.full_clean()

    def test_direct_save_cannot_advertise_unimplemented_capability(self):
        with self.assertRaises(ValidationError):
            ComponentVersion.objects.create(key="login-v1", family="login", version=1,
                                            title="로그인", description="아직 없는 기능",
                                            implementation=Implementation.TEXT_SEARCH,
                                            capabilities=["account.login"], surfaces=[Surface.USER],
                                            status=ComponentVersion.Status.AVAILABLE)
        self.assertFalse(ComponentVersion.objects.filter(key="login-v1").exists())
