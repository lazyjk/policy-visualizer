"""
Flow API routes.

POST /api/flow    — compile a service from an uploaded XML file into Flow IR JSON
POST /api/services — list all services in an uploaded XML file
GET  /api/health  — liveness check

Supports both ClearPass (TipsContents) and Cisco ISE (Root/policysets) XML formats.
Format is auto-detected from the file contents.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from xml.etree.ElementTree import ParseError as XMLParseError

import defusedxml.common

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from api.schemas import FlowEdgeSchema, FlowIRSchema, FlowNodeSchema, HealthResponse, PolicyDetailsSchema, ServiceListResponse, ServiceSummary
from api.schemas_builder import BuilderFromIRRequest
from src.flow_ir import compile_service
from src.ise_flow_ir import ise_compile_policy_set
from src.ise_parser import ise_parse
from src.ise_policy_ir import ise_build
from src.normalizer import And, Op, Or, Predicate
from src.parser import parse
from src.policy_details import build_clearpass_details, build_ise_details
from src.policy_ir import (
    ApplyProfiles,
    AuthMethod,
    AuthSource,
    EnforcementPolicy,
    EnforcementProfile,
    PolicyIR,
    PolicyRule,
    Role,
    RuleFlow,
    Service,
    ServiceAuthentication,
    SetRole,
    RoleMappingPolicy,
    build,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_EXTENSIONS = {".xml"}


def _check_upload(file: UploadFile) -> None:
    """Raise 415 if the file does not have an .xml extension."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only .xml files are accepted.")


def _read_upload(file: UploadFile) -> bytes:
    """Read upload into memory, raising 413 if it exceeds MAX_UPLOAD_BYTES."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    return data


def _detect_format(data: bytes) -> str:
    """Detect whether the XML is ClearPass or ISE format from a content prefix scan."""
    snippet = data[:2000].decode("utf-8", errors="ignore")
    if "<policysets>" in snippet or "<radiusPolicySets>" in snippet:
        return "ise"
    if "avendasys.com" in snippet or "TipsContents" in snippet:
        return "clearpass"
    raise HTTPException(status_code=422, detail="Unrecognized XML format (not ClearPass or ISE).")


def _parse_and_build_clearpass(data: bytes, filename: str):
    """Parse ClearPass XML bytes into (raw, ir). Raises 4xx on error."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        raw = parse(tmp_path)
        ir = build(raw, source_file=filename)
    except (XMLParseError, defusedxml.common.DefusedXmlException) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Processing error.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return raw, ir


def _parse_and_build_ise(data: bytes, filename: str):
    """Parse ISE XML bytes into (raw, ir). Raises 4xx on error."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        raw = ise_parse(tmp_path)
        ir = ise_build(raw, source_file=filename)
    except (XMLParseError, defusedxml.common.DefusedXmlException) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Processing error.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return raw, ir


def _flow_ir_to_schema(flow, warnings: list[str], details: PolicyDetailsSchema | None = None) -> FlowIRSchema:
    nodes = [
        FlowNodeSchema(
            id=n.id,
            type=n.type,
            label=n.label,
            sub_label=n.sub_label,
            trace_rule_id=n.trace_rule_id,
            rank_group=n.rank_group,
        )
        for n in flow.nodes
    ]
    edges = [
        FlowEdgeSchema(from_id=e.from_id, to_id=e.to_id, label=e.label, reason=e.reason)
        for e in flow.edges
    ]
    return FlowIRSchema(
        service_id=flow.service_id,
        service_name=flow.service_name,
        service_type=flow.service_type,
        nodes=nodes,
        edges=edges,
        warnings=warnings,
        details=details,
    )


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@router.post("/services", response_model=ServiceListResponse)
async def list_services(file: UploadFile = File(...)):
    """Return the list of services (or ISE policy sets) found in the uploaded XML file."""
    _check_upload(file)
    data = _read_upload(file)
    fmt = _detect_format(data)

    if fmt == "ise":
        _, ir = _parse_and_build_ise(data, file.filename or "")
        services = [
            ServiceSummary(id=ps.id, name=ps.name, description=ps.description, service_type=ps.set_type)
            for ps in ir.policy_sets
        ]
    else:
        _, ir = _parse_and_build_clearpass(data, file.filename or "")
        services = [
            ServiceSummary(id=s.id, name=s.name, description=s.description, service_type=s.service_type)
            for s in ir.services.values()
        ]

    if not services:
        raise HTTPException(status_code=422, detail="No services found in the uploaded XML.")
    return ServiceListResponse(services=services)


@router.post("/flow", response_model=FlowIRSchema)
async def get_flow(
    file: UploadFile = File(...),
    service: str | None = Query(default=None, description="Service ID to render. Defaults to the first service."),
    include_details: bool = Query(default=False, description="Include detailed rule data for inspector and appendix export."),
):
    """Compile an uploaded XML file into a Flow IR for rendering."""
    _check_upload(file)
    data = _read_upload(file)
    fmt = _detect_format(data)

    if fmt == "ise":
        _, ir = _parse_and_build_ise(data, file.filename or "")
        if not ir.policy_sets:
            raise HTTPException(status_code=422, detail="No policy sets found in the uploaded XML.")
        if service:
            ps = next((p for p in ir.policy_sets if p.id == service), None)
            if ps is None:
                available = [p.id for p in ir.policy_sets]
                raise HTTPException(
                    status_code=404,
                    detail=f"Policy set '{service}' not found. Available: {available}",
                )
        else:
            ps = ir.policy_sets[0]
        flow = ise_compile_policy_set(ps, ir)
        details = PolicyDetailsSchema.model_validate(build_ise_details(ps, ir)) if include_details else None
        return _flow_ir_to_schema(flow, ir.warnings, details)

    else:
        _, ir = _parse_and_build_clearpass(data, file.filename or "")
        if not ir.services:
            raise HTTPException(status_code=422, detail="No services found in the uploaded XML.")
        if service:
            svc = ir.services.get(service)
            if svc is None:
                available = list(ir.services.keys())
                raise HTTPException(
                    status_code=404,
                    detail=f"Service '{service}' not found. Available: {available}",
                )
        else:
            svc = next(iter(ir.services.values()))
        flow = compile_service(svc, ir)
        details = PolicyDetailsSchema.model_validate(build_clearpass_details(svc, ir)) if include_details else None
        return _flow_ir_to_schema(flow, ir.warnings, details)


# ---------------------------------------------------------------------------
# Builder canvas → Flow IR (preview endpoint)
# ---------------------------------------------------------------------------


def _builder_condition_to_bool_expr(cond_expr):
    """Convert a BuilderConditionExpr into a BooleanExpr (And/Or/Predicate)."""
    if cond_expr is None or not cond_expr.conditions:
        return And(operands=[])

    predicates = []
    for c in cond_expr.conditions:
        try:
            op = Op(c.op)
        except ValueError:
            op = Op.equals
        predicates.append(
            Predicate(
                namespace=c.namespace,
                attribute=c.attribute,
                op=op,
                rhs_raw=c.value,
                rhs_display=c.value,
            )
        )

    if len(predicates) == 1:
        return predicates[0]

    combinator = (cond_expr.combinator or "and").lower()
    if combinator == "or":
        return Or(operands=predicates)
    return And(operands=predicates)


def _builder_payload_to_policy_ir(req: BuilderFromIRRequest):
    """Convert a BuilderFromIRRequest into a (Service, PolicyIR) tuple."""
    import hashlib, re

    def _sid(name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
        suffix = hashlib.sha256(name.encode()).hexdigest()[:6]
        return f"{slug}_{suffix}" if slug else f"id_{suffix}"

    ir = PolicyIR(version="1.0", source_file="builder")

    # Roles
    for r in req.roles:
        ir.roles[r.id] = Role(id=r.id, name=r.name)

    # Auth methods + sources
    for m in req.auth.methods:
        ir.auth_methods[m.id] = AuthMethod(id=m.id, name=m.name, method_type="")
    for s in req.auth.sources:
        ir.auth_sources[s.id] = AuthSource(id=s.id, name=s.name, source_type="")

    # Enforcement profiles
    for p in req.enforcement_profiles:
        ir.enforcement_profiles[p.id] = EnforcementProfile(
            id=p.id, name=p.name, profile_type=p.profile_type
        )

    # Role mapping policy
    rm = req.role_mapping_policy
    rm_id = rm.id or _sid(rm.name)
    rm_rules: list[PolicyRule] = []
    for idx, rule in enumerate(rm.rules):
        when = _builder_condition_to_bool_expr(rule.condition)
        action = SetRole(
            role_id=rule.role_action.role_id if rule.role_action else "",
            role_name=rule.role_action.role_name if rule.role_action else "",
        )
        rm_rules.append(PolicyRule(
            id=rule.id,
            index=idx,
            when=when,
            then=action,
            flow=RuleFlow(on_match=rule.on_match),
        ))
    rm_default = SetRole(
        role_id=rm.default_role_id,
        role_name=rm.default_role_name,
    )
    rm_policy = RoleMappingPolicy(
        id=rm_id, name=rm.name, rule_combine_algo="first-applicable",
        rules=rm_rules, default=rm_default,
    )
    ir.role_mapping_policies[rm_id] = rm_policy

    # Enforcement policy
    ep = req.enforcement_policy
    ep_id = ep.id or _sid(ep.name)
    ep_rules: list[PolicyRule] = []
    for idx, rule in enumerate(ep.rules):
        when = _builder_condition_to_bool_expr(rule.condition)
        action = ApplyProfiles(
            profile_ids=rule.enforcement_action.profile_ids if rule.enforcement_action else [],
            profile_names=rule.enforcement_action.profile_names if rule.enforcement_action else [],
        )
        ep_rules.append(PolicyRule(
            id=rule.id,
            index=idx,
            when=when,
            then=action,
            flow=RuleFlow(on_match=rule.on_match),
        ))
    ep_default = ApplyProfiles(
        profile_ids=ep.default_profile_ids,
        profile_names=ep.default_profile_names,
    )
    ep_policy = EnforcementPolicy(
        id=ep_id, name=ep.name, policy_type="radius",
        rule_combine_algo="first-applicable",
        rules=ep_rules, default=ep_default,
    )
    ir.enforcement_policies[ep_id] = ep_policy

    # Service
    svc_id = _sid(req.service.name)
    svc_match = _builder_condition_to_bool_expr(req.service.match)
    svc = Service(
        id=svc_id,
        name=req.service.name,
        description=req.service.description,
        service_type=req.service.service_type,
        match=svc_match,
        authentication=ServiceAuthentication(
            method_ids=[m.id for m in req.auth.methods],
            method_names=[m.name for m in req.auth.methods],
            source_ids=[s.id for s in req.auth.sources],
            source_names=[s.name for s in req.auth.sources],
        ),
        role_mapping_policy_id=rm_id,
        role_mapping_policy_name=rm.name,
        enforcement_policy_id=ep_id,
        enforcement_policy_name=ep.name,
    )
    ir.services[svc_id] = svc

    return svc, ir


@router.post("/flow/from-ir", response_model=FlowIRSchema)
def flow_from_builder_ir(req: BuilderFromIRRequest):
    """Compile a builder canvas payload into Flow IR for preview rendering.

    Accepts the canvas state JSON from the Policy Builder and returns the
    same FlowIR JSON schema as POST /api/flow — no XML upload required.
    """
    try:
        svc, ir = _builder_payload_to_policy_ir(req)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid builder payload: {exc}") from exc

    try:
        flow = compile_service(svc, ir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Flow compilation error.") from exc

    return _flow_ir_to_schema(flow, ir.warnings)
