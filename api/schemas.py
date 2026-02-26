"""
Pydantic schemas for the FastAPI response models.
Mirrors the FlowIR dataclass structure for JSON serialization.
"""
from __future__ import annotations

from pydantic import BaseModel


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
    label: str = ""


class FlowIRSchema(BaseModel):
    service_id: str
    service_name: str
    service_type: str = "RADIUS"
    nodes: list[FlowNodeSchema]
    edges: list[FlowEdgeSchema]
    warnings: list[str] = []


class ServiceSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    service_type: str = "RADIUS"


class ServiceListResponse(BaseModel):
    services: list[ServiceSummary]


class HealthResponse(BaseModel):
    status: str
