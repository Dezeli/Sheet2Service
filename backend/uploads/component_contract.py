"""Finite registry vocabulary for capabilities already implemented by the runtime.

Adding a new implementation here does not make it executable. The runtime must first
provide and test the behavior that a registered component claims to support.
"""

from enum import StrEnum


class Surface(StrEnum):
    DASHBOARD = "dashboard"
    USER = "user"
    ADMIN = "admin"
    PLATFORM = "platform"


class Capability(StrEnum):
    CATALOG_LIST = "catalog.list"
    CATALOG_DETAIL = "catalog.detail"
    CATALOG_SEARCH = "catalog.search_text"
    CATALOG_FILTER = "catalog.filter_exact"
    CHART_COUNT_BY = "chart.count_by"
    SUBMISSION_CREATE = "submission.create"
    SUBMISSION_VIEW = "submission.view"
    SUBMISSION_TRANSITION = "submission.transition"
    CATALOG_EDIT = "catalog.edit_rows"
    FIELD_RENAME = "catalog.rename_field"
    CHOICE_MANAGE = "catalog.manage_choices"
    ACCOUNT_REGISTER = "account.register"
    ACCOUNT_LOGIN = "account.login"
    ACCOUNT_ACCESS_CONTROL = "account.access_control"
    MAP_MARKERS = "map.markers"
    RESERVATION_TIME_SLOT = "reservation.time_slot"
    RESERVATION_CAPACITY = "reservation.capacity"


class Implementation(StrEnum):
    CATALOG_BROWSER = "catalog_browser"
    TEXT_SEARCH = "text_search"
    EXACT_FILTER = "exact_filter"
    COUNT_CHART = "count_chart"
    SUBMISSION_FORM = "submission_form"
    SUBMISSION_STATUS = "submission_status"
    CATALOG_MANAGEMENT = "catalog_management"


IMPLEMENTATION_CAPABILITIES = {
    Implementation.CATALOG_BROWSER: frozenset((Capability.CATALOG_LIST, Capability.CATALOG_DETAIL)),
    Implementation.TEXT_SEARCH: frozenset((Capability.CATALOG_SEARCH,)),
    Implementation.EXACT_FILTER: frozenset((Capability.CATALOG_FILTER,)),
    Implementation.COUNT_CHART: frozenset((Capability.CHART_COUNT_BY,)),
    Implementation.SUBMISSION_FORM: frozenset((Capability.SUBMISSION_CREATE,)),
    Implementation.SUBMISSION_STATUS: frozenset((Capability.SUBMISSION_VIEW, Capability.SUBMISSION_TRANSITION)),
    Implementation.CATALOG_MANAGEMENT: frozenset((Capability.CATALOG_EDIT, Capability.FIELD_RENAME,
                                                   Capability.CHOICE_MANAGE)),
}


IMPLEMENTATION_SURFACES = {
    Implementation.CATALOG_BROWSER: frozenset((Surface.USER,)),
    Implementation.TEXT_SEARCH: frozenset((Surface.USER,)),
    Implementation.EXACT_FILTER: frozenset((Surface.USER,)),
    Implementation.COUNT_CHART: frozenset((Surface.DASHBOARD,)),
    Implementation.SUBMISSION_FORM: frozenset((Surface.USER,)),
    Implementation.SUBMISSION_STATUS: frozenset((Surface.USER, Surface.ADMIN)),
    Implementation.CATALOG_MANAGEMENT: frozenset((Surface.ADMIN,)),
}


def valid_component_contract(implementation, capabilities, surfaces):
    """A DB row can advertise only the behavior wired to its approved adapter."""
    if not isinstance(capabilities, list) or not isinstance(surfaces, list):
        return False
    try:
        adapter = Implementation(implementation)
        capability_set = {Capability(item) for item in capabilities}
        surface_set = {Surface(item) for item in surfaces}
    except (ValueError, TypeError):
        return False
    return bool(capability_set and surface_set) and len(capability_set) == len(capabilities) \
        and len(surface_set) == len(surfaces) \
        and capability_set == IMPLEMENTATION_CAPABILITIES[adapter] \
        and surface_set == IMPLEMENTATION_SURFACES[adapter]
