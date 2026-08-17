"""Dynamic field discovery for Jira instances.

Calls `GET /rest/api/3/field` on a Jira instance and normalizes the result into a
list of dicts: {id, name, type, is_custom, schema_type, schema_custom}.

Jira returns both system fields ("status", "priority", "assignee", …) and custom
fields ("customfield_10086", …) in one call — no pagination needed.
"""
from __future__ import annotations

import requests
from requests.auth import HTTPBasicAuth


# Jira "schema.type" → our app-level type. The schema.type for long text fields
# (textarea, multi-line) is also "string", so we also need to look at the
# `schema.custom` attribute — see `normalize_field` below.
_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "datetime": "datetime",
    "date": "datetime",
    "number": "number",
    "integer": "number",
    "decimal": "number",
    "float": "number",
    "anytype": "string",
    "option": "string",
    "options": "string",
    "array": "string",
    "user": "string",
    "users": "string",
    "group": "string",
    "groups": "string",
    "project": "string",
    "version": "string",
    "versions": "string",
    "issuetype": "string",
    "priority": "string",
    "status": "string",
    "resolution": "string",
    "labels": "string",
    "issuelinks": "string",
    "attachment": "string",
    "url": "string",
    "component": "string",
    "components": "string",
    "securitylevel": "string",
    "progress": "number",
    "timeestimate": "number",
    "timespent": "number",
    "aggregatetimespent": "number",
    "aggregatetimeoriginalestimate": "number",
    "aggregatetimeestimate": "number",
    "workratio": "number",
    "watches": "number",
    "votes": "number",
    "comment": "text",
    "description": "text",
    "environment": "text",
    "textarea": "text",
    "readonlyfield": "string",
    "multiversion": "string",
    "multiselect": "string",
    "multiuserpicker": "string",
    "multigrouppicker": "string",
    "multicheckboxes": "string",
    "radiobuttons": "string",
    "select": "string",
    "cascadingselect": "string",
    "userpicker": "string",
    "grouppicker": "string",
    "datepicker": "datetime",
}

# Jira custom field type keys (the trailing segment of `schema.custom`) that
# are clearly long-text. If schema.custom matches any of these we treat the
# field as "text" regardless of schema.type.
_TEXTAREA_CUSTOM_KEYS = {
    "textarea",
    "textfield",  # multi-line text fields
    "readonlytextarea",
}

# Standard Jira system fields whose values are always long text. These don't
# have a `schema.custom` (they're not custom fields), but they can easily run
# past VARCHAR(255).
_KNOWN_LONG_TEXT_FIELDS = {
    "summary",
    "description",
    "environment",
    "comment",
}


def normalize_field(raw: dict) -> dict | None:
    """Map one raw Jira field record to {id, name, type, is_custom, schema_type, schema_custom}.

    Jira's schema.type is "string" for both single-line and multi-line text fields
    (and for a bunch of other things), so we also inspect `schema.custom` to
    detect textareas. The `schema.custom` for a custom textarea looks like
    `com.atlassian.jira.plugin.system.customfieldtypes:textarea`.
    """
    field_id = raw.get("id")
    name = raw.get("name")
    if not field_id or not name:
        return None
    schema = raw.get("schema") or {}
    schema_type = (schema.get("type") or "").lower() or None
    schema_custom = schema.get("custom")  # None for system fields

    # First, the basic type from schema.type.
    our_type = _TYPE_MAP.get(schema_type or "", "string")

    # Override: if schema.custom says this is a textarea, force "text".
    if schema_custom:
        custom_key = schema_custom.rsplit(":", 1)[-1].lower()
        if custom_key in _TEXTAREA_CUSTOM_KEYS:
            our_type = "text"

    # Fallback for standard Jira long-text fields (they have no schema.custom).
    if field_id in _KNOWN_LONG_TEXT_FIELDS:
        our_type = "text"

    return {
        "field_id": field_id,
        "name": name,
        "field_type": our_type,
        "is_custom": bool(raw.get("custom")),
        "schema_type": schema_type,
        "schema_custom": schema_custom,
    }


class JiraFieldFetchError(RuntimeError):
    pass


def fetch_instance_fields(domain: str, email: str, token: str) -> list[dict]:
    """Call `GET /rest/api/3/field` and return the normalized field list.

    Raises JiraFieldFetchError on HTTP errors. Jira returns all fields in one call.
    """
    from .client import _get_json_with_retry

    url = f"https://{domain}/rest/api/3/field"
    auth = HTTPBasicAuth(email, token)
    raw_fields = _get_json_with_retry("Jira /field", url, auth) or []
    out: list[dict] = []
    for raw in raw_fields:
        n = normalize_field(raw)
        if n:
            out.append(n)
    return out


def fetch_myself(domain: str, email: str, token: str) -> dict:
    """Call `GET /rest/api/3/myself` to verify connectivity and return the user.

    Raises JiraFieldFetchError on HTTP errors.
    """
    from .client import _get_json_with_retry

    url = f"https://{domain}/rest/api/3/myself"
    auth = HTTPBasicAuth(email, token)
    data = _get_json_with_retry("Jira /myself", url, auth) or {}
    return {
        "account_id": data.get("accountId"),
        "display_name": data.get("displayName"),
        "email": data.get("emailAddress"),
    }
