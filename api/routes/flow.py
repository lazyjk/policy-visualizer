"""
Flow API routes.

POST /api/flow    — compile a service from an uploaded XML file into Flow IR JSON
POST /api/services — list all services in an uploaded XML file
GET  /api/health  — liveness check
"""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path
from xml.etree.ElementTree import ParseError as XMLParseError

import defusedxml.common

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from api.schemas import FlowEdgeSchema, FlowIRSchema, FlowNodeSchema, HealthResponse, ServiceListResponse, ServiceSummary
from src.flow_ir import compile_service
from src.parser import parse
from src.policy_ir import build

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


def _parse_and_build(file: UploadFile):
    """Validate, read, and parse the XML upload; return (raw, ir) or raise 4xx."""
    _check_upload(file)
    data = _read_upload(file)

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        raw = parse(tmp_path)
        ir = build(raw, source_file=file.filename or "")
    except (XMLParseError, defusedxml.common.DefusedXmlException) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid XML: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Processing error.") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return raw, ir


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")


@router.post("/services", response_model=ServiceListResponse)
async def list_services(file: UploadFile = File(...)):
    """Return the list of services found in the uploaded XML file."""
    _, ir = _parse_and_build(file)
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
    service: str | None = Query(default=None, description="Service name to render. Defaults to the first service."),
):
    """Compile a ClearPass XML upload into a Flow IR for rendering."""
    _, ir = _parse_and_build(file)

    if not ir.services:
        raise HTTPException(status_code=422, detail="No services found in the uploaded XML.")

    if service:
        svc = next((s for s in ir.services.values() if s.name == service), None)
        if svc is None:
            available = [s.name for s in ir.services.values()]
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service}' not found. Available: {available}",
            )
    else:
        svc = next(iter(ir.services.values()))

    flow = compile_service(svc, ir)

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
        FlowEdgeSchema(from_id=e.from_id, to_id=e.to_id, label=e.label)
        for e in flow.edges
    ]
    return FlowIRSchema(
        service_id=flow.service_id,
        service_name=flow.service_name,
        service_type=flow.service_type,
        nodes=nodes,
        edges=edges,
        warnings=ir.warnings,
    )
