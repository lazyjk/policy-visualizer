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


class RuleDetailSchema(BaseModel):
    rule_id: str
    node_trace_id: str
    index: int
    name: str = ""
    condition_text: str
    action_text: str
    on_match: str = "stop"
    linked_names: list[str] = []


class ServiceContextSchema(BaseModel):
    service_name: str
    service_type: str
    description: str = ""
    auth_method_names: list[str] = []
    auth_source_names: list[str] = []
    condition_text: str


class PolicyDetailsSchema(BaseModel):
    service_context: ServiceContextSchema
    authen_rules: list[RuleDetailSchema] = []
    role_mapping_rules: list[RuleDetailSchema] = []
    enforcement_rules: list[RuleDetailSchema] = []
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


class ServiceListResponse(BaseModel):
    services: list[ServiceSummary]


class HealthResponse(BaseModel):
    status: str
