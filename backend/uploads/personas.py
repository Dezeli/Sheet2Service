"""The roles of a reservation service, fixed in code so no two roles share a duty.

The model only names the booker and may point at a column that splits the staff's work (a branch,
an organization, a person in charge). Which roles exist and what each may do is decided here:

- booker   예약자        reserves, keeps their bookings, asks, reads notices
- operator 예약 담당자    the desk: home, approving and declining, the schedule board, answering inquiries
- admin    시스템 관리자   setting up: items, sessions, booking rules, notices, the service name, the sheet's data
- finance  정산 담당자    payments; only when the sheet records payment or amounts
- field    현장 담당자    today's list, check-in and completion; only when the sheet records use or completion,
                         otherwise those steps stay with the operator
"""

MONEY_ROLES = ("payment", "amount")
FIELD_KINDS = ("in_use", "completed")
TITLES = {"booker": "예약자", "operator": "예약 담당자", "admin": "시스템 관리자", "finance": "정산 담당자", "field": "현장 담당자"}
BOOKER = ["browse_resources", "make_reservation", "my_reservations", "inquiry", "notices"]
OPERATOR = ["dashboard", "review_reservations", "reply_inquiries"]
ADMIN = ["manage_resources", "manage_schedule", "manage_notices", "manage_data"]
FINANCE = ["manage_payments"]
FIELD = ["run_sessions"]
ROLE_ORDER = ("booker", "operator", "field", "finance", "admin", "viewer")
# which booking steps belong to which duty
STEP_FEATURES = {"approve": "review_reservations", "reject": "review_reservations", "cancel": "review_reservations",
                 "reopen": "review_reservations", "check_in": "run_sessions", "complete": "run_sessions"}


def may_take(persona, action):
    """Whether this role may move a booking by this step (a booker's own cancel is checked elsewhere)."""
    feature = STEP_FEATURES.get(action)
    return bool(feature) and feature in persona.get("features", [])


def standard_personas(personas, column_roles, states, *, reservable=True, accepts_bookings=True, paid=None):
    """The roles a service gets, from the model's suggestion and what the sheet holds.

    paid says whether the records actually charge money; unknown (None) trusts the payment columns."""
    if not reservable:  # a record-only sheet keeps its viewer and admin as they are
        return personas
    by_id = {persona.get("id"): persona for persona in personas}
    booker = by_id.get("booker") or by_id.get("viewer") or {}
    # a column the staff's work splits by: kept on the operator, who may then narrow to one part (or see all)
    scope = next((persona.get("scopeColumn") for persona in personas
                  if persona.get("id") in ("operator", "staff", "org_manager") and persona.get("scopeColumn")), 0)
    has_money = any(role in MONEY_ROLES for role in column_roles) and paid is not False
    has_field = any(state.get("kind") in FIELD_KINDS for state in states)

    def role(role_id, features, title=None, evidence="", scope_column=0):
        return {"id": role_id, "title": title or TITLES[role_id], "scopeColumn": scope_column, "features": list(features),
                "evidence": evidence}

    booker_features = BOOKER if accepts_bookings else [f for f in BOOKER if f not in ("make_reservation", "my_reservations")]
    result = [role("booker", booker_features, booker.get("title") if booker.get("id") == "booker" else None, booker.get("evidence", "")),
              role("operator", OPERATOR + ([] if has_field else FIELD), scope_column=scope),
              role("admin", ADMIN, evidence=by_id.get("admin", {}).get("evidence", ""))]
    if has_field:
        result.append(role("field", FIELD))
    if has_money:
        result.append(role("finance", FINANCE, evidence=by_id.get("finance", {}).get("evidence", "")))
    order = {role_id: index for index, role_id in enumerate(ROLE_ORDER)}
    return sorted(result, key=lambda persona: order[persona["id"]])
