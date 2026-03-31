"""Pydantic models for ClearPass REST API response normalization.

These models accept all known field name variants returned by ClearPass
across different firmware versions, and always emit a single canonical shape.
Upstream code (clearpass_client.py) parses every API response through the
appropriate model so that downstream code (BuilderView.tsx) never needs to
guess at field names.

Canonical field names emitted by each model are the ground truth for the
TypeScript interfaces in frontend/src/api/builderApi.ts.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _first(*values: Any) -> str:
    """Return the first non-None, non-empty string from the given values."""
    for v in values:
        if v is None:
            continue
        s = str(v)
        if s:
            return s
    return ""


def _to_str_list(val: Any) -> list[str]:
    """Coerce a string or list-of-strings to list[str]."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val else []
    if isinstance(val, list):
        return [str(x) for x in val if x is not None]
    return []


# ---------------------------------------------------------------------------
# Base model with integer-ID coercion
# ---------------------------------------------------------------------------


class _CPBase(BaseModel):
    """Base class that coerces ``id`` from int → str (ClearPass returns numeric IDs)."""

    @field_validator("id", mode="before", check_fields=False)
    @classmethod
    def _coerce_id(cls, v: Any) -> Any:
        if v is None:
            return ""
        return str(v)


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------


class CPCondition(BaseModel):
    """A single condition predicate, normalized from all ClearPass field variants.

    ClearPass REST API field name variants observed across firmware versions:
      namespace : ``type``  (most common) | ``namespace``
      attribute : ``name``                | ``attribute``  | ``attr_name``
      operator  : ``oper``  (REST API)    | ``operator``   | ``attr_oper``
      value     : ``value``               | ``attr_value``
    """

    model_config = ConfigDict(extra="ignore")

    namespace: str = ""
    attribute: str = ""
    operator: str = ""   # uppercase ClearPass operator, e.g. "EQUALS"
    value: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        namespace = _first(d.pop("type", None), d.pop("namespace", None))
        attribute = _first(d.pop("name", None), d.pop("attribute", None), d.pop("attr_name", None))
        operator = _first(d.pop("oper", None), d.pop("operator", None), d.pop("attr_oper", None))
        value = _first(d.pop("value", None), d.pop("attr_value", None))
        d["namespace"] = namespace
        d["attribute"] = attribute
        d["operator"] = operator
        d["value"] = value
        return d


class CPAuthItem(_CPBase):
    """An {id, name} pair used for auth methods, auth sources, and roles.

    Accepts a plain string (treated as both id and name) or a dict.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"id": data, "name": data}
        if isinstance(data, dict):
            name = _first(data.get("name"), data.get("id"))
            return {"id": _first(data.get("id"), name), "name": name}
        return data


class CPLinkedPolicy(_CPBase):
    """A reference to a linked policy object (name string or {id, name} dict)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"id": "", "name": data}
        if isinstance(data, dict):
            return {
                "id": _first(data.get("id")),
                "name": _first(data.get("name"), data.get("id")),
            }
        return {"id": "", "name": ""}


# ---------------------------------------------------------------------------
# List-item models (from HAL collection pages)
# ---------------------------------------------------------------------------


class CPRoleItem(_CPBase):
    """Minimal role item from GET /api/role collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class CPAuthMethodItem(_CPBase):
    """Minimal auth method item from GET /api/auth-method collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class CPAuthSourceItem(_CPBase):
    """Minimal auth source item from GET /api/auth-source collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class CPEnforcementProfileItem(_CPBase):
    """Enforcement profile item from GET /api/enforcement-profile collection.

    ClearPass returns ``profile_type`` values such as ``radius_accept``,
    ``radius_reject``, ``post_auth``, ``tacacs_accept``, ``tacacs_other``.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    profile_type: str = "radius_accept"


class CPEnforcementPolicyListItem(_CPBase):
    """Minimal enforcement policy item from GET /api/enforcement-policy collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class CPRoleMappingListItem(_CPBase):
    """Minimal role mapping policy item from GET /api/role-mapping collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""


class CPServiceListItem(_CPBase):
    """Service item from GET /api/config/service collection (minimal fields)."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    service_type: str = "RADIUS"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["service_type"] = _first(
            d.pop("type", None),
            d.pop("template_type", None),
            d.pop("service_type", None),
        )
        return d


# ---------------------------------------------------------------------------
# Policy rule models
# ---------------------------------------------------------------------------


class CPRoleMappingRule(_CPBase):
    """A single rule inside a role mapping policy.

    ClearPass REST API field name variants:
      conditions : ``condition`` (array) | ``conditions`` (array)
      stop_if_match: ``stop_if_match`` (bool) | ``flow.on_match`` == ``"continue"``
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    conditions: list[CPCondition] = []
    match_type: str = "AND"   # "AND" | "OR" | "MATCHES_ALL" | "MATCHES_ANY"
    roles: list[CPAuthItem] = []
    stop_if_match: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # Normalize conditions field name
        if not d.get("conditions"):
            raw_cond = d.pop("condition", None)
            d["conditions"] = raw_cond if isinstance(raw_cond, list) else []

        # Normalize stop_if_match from flow.on_match fallback
        if "stop_if_match" not in d:
            flow = d.get("flow") or {}
            on_match = (flow if isinstance(flow, dict) else {}).get("on_match", "stop")
            d["stop_if_match"] = on_match != "continue"

        return d


class CPEnforcementPolicyRule(_CPBase):
    """A single rule inside an enforcement policy.

    ClearPass REST API field name variants:
      conditions            : ``condition`` | ``conditions``
      enforcement_profile_names: ``enforcement_profile_names`` | ``then.profile_names``
      enforcement_profile_ids  : ``enforcement_profile_ids``   | ``then.profile_ids``
      stop_if_match         : ``stop_if_match`` | ``flow.on_match``
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    conditions: list[CPCondition] = []
    match_type: str = "AND"
    enforcement_profile_names: list[str] = []
    enforcement_profile_ids: list[str] = []
    stop_if_match: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # Normalize conditions
        if not d.get("conditions"):
            raw_cond = d.pop("condition", None)
            d["conditions"] = raw_cond if isinstance(raw_cond, list) else []

        # Normalize profile names — REST API uses enforcement_profile_names;
        # Policy IR fallback uses then.profile_names
        if not d.get("enforcement_profile_names"):
            then = d.get("then") or {}
            then_names = (then if isinstance(then, dict) else {}).get("profile_names") or []
            d["enforcement_profile_names"] = _to_str_list(then_names)

        # Normalize profile ids — REST API uses enforcement_profile_ids;
        # Policy IR fallback uses then.profile_ids
        if not d.get("enforcement_profile_ids"):
            then = d.get("then") or {}
            then_ids = (then if isinstance(then, dict) else {}).get("profile_ids") or []
            d["enforcement_profile_ids"] = _to_str_list(then_ids)

        # Normalize stop_if_match
        if "stop_if_match" not in d:
            flow = d.get("flow") or {}
            on_match = (flow if isinstance(flow, dict) else {}).get("on_match", "stop")
            d["stop_if_match"] = on_match != "continue"

        return d


# ---------------------------------------------------------------------------
# Full policy detail models
# ---------------------------------------------------------------------------


class CPRoleMappingPolicy(_CPBase):
    """Full role mapping policy detail from GET /api/role-mapping/{id}.

    ClearPass REST API field name variants:
      default_role : ``default_role`` {id, name} | ``default_role_id`` + ``default_role_name``
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    rules: list[CPRoleMappingRule] = []
    default_role: CPAuthItem = CPAuthItem()

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # Normalize default_role: may be {id, name} dict or flat id/name fields
        if not d.get("default_role"):
            d["default_role"] = {
                "id": _first(d.get("default_role_id")),
                "name": _first(d.get("default_role_name"), d.get("default_role_id")),
            }

        return d


class CPEnforcementPolicy(_CPBase):
    """Full enforcement policy detail from GET /api/enforcement-policy/{id}.

    Default profile field name variants observed across ClearPass versions:
      string  : ``default_enforcement_profile`` = "[Deny Access Profile]"
      array   : ``default_enforcement_profiles`` = ["[Deny Access Profile]"]
      object  : ``default`` = {profile_names: [...], profile_ids: [...]}
      array   : ``default_enforcement_profile_ids`` = [...]

    All variants are normalized to:
      ``default_enforcement_profile_names: list[str]``
      ``default_enforcement_profile_ids:   list[str]``
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    rules: list[CPEnforcementPolicyRule] = []
    default_enforcement_profile_names: list[str] = []
    default_enforcement_profile_ids: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # Normalize default profile names
        if not d.get("default_enforcement_profile_names"):
            raw_default = d.get("default_enforcement_profile") or d.get("default_enforcement_profiles")
            if raw_default is None:
                default_obj = d.get("default") or {}
                raw_default = (default_obj if isinstance(default_obj, dict) else {}).get("profile_names")
            d["default_enforcement_profile_names"] = _to_str_list(raw_default)

        # Normalize default profile ids
        if not d.get("default_enforcement_profile_ids"):
            raw_ids = d.get("default_enforcement_profile_ids")
            if raw_ids is None:
                default_obj = d.get("default") or {}
                raw_ids = (default_obj if isinstance(default_obj, dict) else {}).get("profile_ids")
            d["default_enforcement_profile_ids"] = _to_str_list(raw_ids)

        return d


class CPService(_CPBase):
    """Full service detail from GET /api/config/service/{id}.

    ClearPass REST API field name variants:
      service_type       : ``type`` | ``template_type`` | ``service_type``
      rules_conditions   : ``rules_conditions`` | ``conditions`` | ``condition``
                         | ``match_conditions``
      rules_match_type   : ``rules_match_type`` | ``match_type``
      authentication_methods : ``authentication_methods`` | ``auth_methods``
      authentication_sources : ``authentication_sources`` | ``authorization_sources``
                             | ``auth_sources``
      role_mapping_policy    : ``role_mapping_policy`` | ``role_mapping_policies``
      enf_policy             : ``enf_policy`` | ``enforcement_policy``
                             | ``authorization_policy``
    """

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = ""
    service_type: str = "RADIUS"
    description: str = ""
    rules_conditions: list[CPCondition] = []
    rules_match_type: str = "MATCHES_ALL"
    authentication_methods: list[CPAuthItem] = []
    authentication_sources: list[CPAuthItem] = []
    role_mapping_policy: CPLinkedPolicy = CPLinkedPolicy()
    enf_policy: CPLinkedPolicy = CPLinkedPolicy()

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # service_type
        d["service_type"] = _first(
            d.pop("type", None),
            d.pop("template_type", None),
            d.pop("service_type", None),
        )

        # rules_conditions
        if not d.get("rules_conditions"):
            d["rules_conditions"] = (
                d.pop("conditions", None)
                or d.pop("condition", None)
                or d.pop("match_conditions", None)
                or []
            )

        # rules_match_type
        if not d.get("rules_match_type"):
            d["rules_match_type"] = _first(d.pop("match_type", None)) or "MATCHES_ALL"

        # authentication_methods
        if not d.get("authentication_methods"):
            d["authentication_methods"] = d.pop("auth_methods", None) or []

        # authentication_sources
        if not d.get("authentication_sources"):
            d["authentication_sources"] = (
                d.pop("authorization_sources", None)
                or d.pop("auth_sources", None)
                or []
            )

        # role_mapping_policy
        if not d.get("role_mapping_policy"):
            d["role_mapping_policy"] = (
                d.pop("role_mapping_policies", None) or {}
            )

        # enf_policy
        if not d.get("enf_policy"):
            d["enf_policy"] = (
                d.pop("enforcement_policy", None)
                or d.pop("authorization_policy", None)
                or {}
            )

        return d
