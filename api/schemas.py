"""
Pydantic schemas for the FastAPI response models.
Mirrors the FlowIR dataclass structure for JSON serialization.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


FlowEdgeLabel = Literal["", "YES", "NO", "FAIL", "PASS", "CONTINUE"]


class FlowNodeSchema(BaseModel):
    id: str
    type: str
    label: str
    sub_label: str = ""
    trace_rule_id: str = ""
    rank_group: str = ""


class FlowEdgeSchema(BaseModel):
    from_id: str
    to_id: str
    label: FlowEdgeLabel = ""
    reason: str = ""      # human-readable cause for conditional edges (e.g. "usernotfound")


class ProfileAttributeSchema(BaseModel):
    name: str
    type: str = ""
    value: str = ""
    display_value: str = ""


class ExtraSettingSchema(BaseModel):
    """Raw setting from the export that this version does not interpret."""
    path: str
    value: str = ""


class ProfileDetailSchema(BaseModel):
    name: str
    profile_type: str = ""
    action: str = ""
    template: str = ""
    product: str = ""            # e.g. "durPluginA" (Aruba Downloadable User Role)
    nad_groups: list[str] = []   # NAD groups the profile is restricted to
    tacacs_services: list[str] = []  # TACACS services granted, e.g. ["shell", "cpass:HTTP"]
    element_type: str = ""       # XML element for unmodelled profile types (profile_type "other")
    attributes: list[ProfileAttributeSchema] = []
    extras: list[ExtraSettingSchema] = []


class RuleDetailSchema(BaseModel):
    rule_id: str
    node_trace_id: str
    index: int
    name: str = ""
    condition_text: str
    action_text: str
    on_match: str = "stop"
    linked_names: list[str] = []
    profiles: list[ProfileDetailSchema] = []


class StripRuleSchema(BaseModel):
    rule: str                     # as configured, e.g. "user:@"
    description: str = ""         # plain-English reading; "" if unrecognised


class ServiceContextSchema(BaseModel):
    service_name: str
    service_type: str
    description: str = ""
    auth_method_names: list[str] = []
    auth_source_names: list[str] = []
    condition_text: str
    # Service settings (ClearPass; ISE fills enabled only via defaults)
    enabled: bool = True
    template: str = ""
    monitor_mode: bool = False
    use_cached_results: bool = False
    strip_username: bool = False
    strip_rules: list[StripRuleSchema] = []
    posture_enabled: bool = False
    profiler_enabled: bool = False
    audit_enabled: bool = False
    authorization_source_names: list[str] = []
    proxy_targets: list[str] = []          # RADIUS proxy services
    proxy_forward_type: str = ""           # e.g. "ROUND_ROBIN"
    proxy_accounting: bool = False         # accounting requests proxied too
    acct_proxy_targets: list[str] = []
    profiler_coa_profile: str = ""         # CoA sent when an endpoint's category changes
    profiler_categories: list[str] = []
    role_mapping_policy_name: str = ""
    enforcement_policy_name: str = ""
    extras: list[ExtraSettingSchema] = []


class PolicyDetailsSchema(BaseModel):
    service_context: ServiceContextSchema
    authen_rules: list[RuleDetailSchema] = []
    role_mapping_rules: list[RuleDetailSchema] = []
    enforcement_rules: list[RuleDetailSchema] = []
    enforcement_default: RuleDetailSchema | None = None
    warnings: list[str] = []
    rule_index: dict[str, RuleDetailSchema] = {}


class FlowIRSchema(BaseModel):
    service_id: str
    service_name: str
    service_type: str = "RADIUS"
    nodes: list[FlowNodeSchema]
    edges: list[FlowEdgeSchema]
    warnings: list[str] = []
    details: PolicyDetailsSchema | None = None


class ServiceSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    service_type: str = "RADIUS"
    enabled: bool = True
    template: str = ""
    is_category: bool = False      # ClearPass "------Name------" divider service
    export_order: int | None = None  # position in the uploaded file (not precedence)
    precedence: int | None = None    # true ClearPass evaluation order (DB backups only)


class ServiceListResponse(BaseModel):
    services: list[ServiceSummary]


class HealthResponse(BaseModel):
    status: str
