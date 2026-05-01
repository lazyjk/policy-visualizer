"""Pydantic schemas for the Policy Builder API endpoints."""
from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ClearPassConnectRequest(BaseModel):
    server_url: str
    client_id: str
    client_secret: str
    verify_ssl: bool = True


class ClearPassElementsRequest(BaseModel):
    server_url: str
    client_id: str
    client_secret: str
    verify_ssl: bool = True


class ISEConnectRequest(BaseModel):
    server_url: str
    username: str
    password: str
    verify_ssl: bool = True


class ISEElementsRequest(BaseModel):
    server_url: str
    username: str
    password: str
    verify_ssl: bool = True


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ConnectResponse(BaseModel):
    success: bool
    platform: str
    version: str | None = None
    error: str | None = None


class ClearPassElementsResponse(BaseModel):
    services: list[dict] = []
    roles: list[dict] = []
    enforcement_profiles: list[dict] = []
    enforcement_policies: list[dict] = []
    role_mapping_policies: list[dict] = []
    auth_methods: list[dict] = []
    auth_sources: list[dict] = []
    warnings: list[str] = []


class ISEElementsResponse(BaseModel):
    radius_policy_sets: list[dict] = []
    tacacs_policy_sets: list[dict] = []
    profiles: list[dict] = []
    identity_stores: list[dict] = []
    warnings: list[str] = []


class ClearPassAttributesRequest(BaseModel):
    server_url: str
    client_id: str
    client_secret: str
    verify_ssl: bool = True


class ClearPassAttributesResponse(BaseModel):
    namespaces: dict[str, list[str]] = {}
    warnings: list[str] = []


class ClearPassPolicyDetailRequest(BaseModel):
    server_url: str
    client_id: str
    client_secret: str
    verify_ssl: bool = True
    policy_type: str  # "role_mapping" | "enforcement"
    policy_id: str


class ClearPassPolicyDetailResponse(BaseModel):
    policy: dict = {}
    warnings: list[str] = []


class ClearPassServiceDetailRequest(BaseModel):
    server_url: str
    client_id: str
    client_secret: str
    verify_ssl: bool = True
    service_id: str


class ClearPassServiceDetailResponse(BaseModel):
    service: dict = {}
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Builder canvas → Flow IR request schema
# ---------------------------------------------------------------------------
# The canvas sends a simplified "builder payload" which is deserialized
# into PolicyIR dataclasses server-side before calling compile_service().


class BuilderCondition(BaseModel):
    """A single leaf predicate from the condition builder."""
    namespace: str
    attribute: str
    op: str           # canonical Op value, e.g. "equals"
    value: str


class BuilderConditionExpr(BaseModel):
    """Flat AND/OR list of predicates (MVP depth = 1)."""
    combinator: str = "and"   # "and" | "or"
    conditions: list[BuilderCondition] = []


class BuilderAuthItem(BaseModel):
    id: str
    name: str


class BuilderRoleMappingAction(BaseModel):
    role_id: str
    role_name: str


class BuilderEnforcementAction(BaseModel):
    profile_ids: list[str] = []
    profile_names: list[str] = []


class BuilderRule(BaseModel):
    id: str
    name: str = ""
    condition: BuilderConditionExpr | None = None   # None = match-all
    role_action: BuilderRoleMappingAction | None = None
    enforcement_action: BuilderEnforcementAction | None = None
    on_match: str = "stop"


class BuilderServicePayload(BaseModel):
    name: str
    service_type: str = "RADIUS"
    description: str = ""
    match: BuilderConditionExpr | None = None


class BuilderAuthPayload(BaseModel):
    methods: list[BuilderAuthItem] = []
    sources: list[BuilderAuthItem] = []


class BuilderRoleMappingPayload(BaseModel):
    id: str = ""
    name: str
    rules: list[BuilderRule] = []
    default_role_id: str = ""
    default_role_name: str = ""


class BuilderEnforcementPayload(BaseModel):
    id: str = ""
    name: str
    rules: list[BuilderRule] = []
    default_profile_ids: list[str] = []
    default_profile_names: list[str] = []


class BuilderRoleItem(BaseModel):
    id: str
    name: str


class BuilderProfileItem(BaseModel):
    id: str
    name: str
    profile_type: str = "radius_accept"


class BuilderFromIRRequest(BaseModel):
    """Canvas state payload sent by the frontend for preview rendering."""
    service: BuilderServicePayload
    auth: BuilderAuthPayload
    role_mapping_policy: BuilderRoleMappingPayload
    enforcement_policy: BuilderEnforcementPayload
    roles: list[BuilderRoleItem] = []
    enforcement_profiles: list[BuilderProfileItem] = []
