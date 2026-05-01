"""Policy Builder API routes.

Proxy endpoints that forward credential-bearing requests to live ClearPass or
ISE instances.  Stateless: credentials are sent per-request and nothing is
stored server-side.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from api.schemas_builder import (
    ClearPassAttributesRequest,
    ClearPassAttributesResponse,
    ClearPassConnectRequest,
    ClearPassElementsRequest,
    ClearPassElementsResponse,
    ClearPassPolicyDetailRequest,
    ClearPassPolicyDetailResponse,
    ClearPassServiceDetailRequest,
    ClearPassServiceDetailResponse,
    ConnectResponse,
    ISEConnectRequest,
    ISEElementsRequest,
    ISEElementsResponse,
)
from src.clearpass_client import ClearPassClient
from src.ise_client import ISEClient

router = APIRouter(prefix="/builder", tags=["builder"])


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _handle_http_status(exc: httpx.HTTPStatusError, platform: str) -> HTTPException:
    if exc.response.status_code in (401, 403):
        return HTTPException(
            status_code=401,
            detail=f"Invalid {platform} credentials",
        )
    return HTTPException(
        status_code=502,
        detail=f"{platform} returned HTTP {exc.response.status_code}",
    )


def _handle_connect_error(exc: httpx.ConnectError | httpx.RequestError, platform: str) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail=f"Cannot reach {platform}: {exc}",
    )


# ---------------------------------------------------------------------------
# ClearPass endpoints
# ---------------------------------------------------------------------------


@router.post("/clearpass/connect", response_model=ConnectResponse)
def clearpass_connect(req: ClearPassConnectRequest) -> ConnectResponse:
    """Test ClearPass connectivity and return version info."""
    try:
        client = ClearPassClient(
            req.server_url, req.client_id, req.client_secret, req.verify_ssl
        )
        version = client.get_version()
        return ConnectResponse(success=True, platform="clearpass", version=version)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ClearPass") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ClearPass") from exc


@router.post("/clearpass/elements", response_model=ClearPassElementsResponse)
def clearpass_elements(req: ClearPassElementsRequest) -> ClearPassElementsResponse:
    """Fetch all policy elements from a live ClearPass instance."""
    try:
        client = ClearPassClient(
            req.server_url, req.client_id, req.client_secret, req.verify_ssl
        )
        data = client.get_all_elements()
        return ClearPassElementsResponse(**data)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ClearPass") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ClearPass") from exc


@router.post("/clearpass/attributes", response_model=ClearPassAttributesResponse)
def clearpass_attributes(req: ClearPassAttributesRequest) -> ClearPassAttributesResponse:
    """Fetch condition attribute dictionaries from a live ClearPass instance."""
    try:
        client = ClearPassClient(
            req.server_url, req.client_id, req.client_secret, req.verify_ssl
        )
        data = client.get_attributes()
        return ClearPassAttributesResponse(**data)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ClearPass") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ClearPass") from exc


@router.post("/clearpass/policy-detail", response_model=ClearPassPolicyDetailResponse)
def clearpass_policy_detail(req: ClearPassPolicyDetailRequest) -> ClearPassPolicyDetailResponse:
    """Fetch full rule detail for a single ClearPass policy (for template loading)."""
    try:
        client = ClearPassClient(
            req.server_url, req.client_id, req.client_secret, req.verify_ssl
        )
        if req.policy_type == "role_mapping":
            policy = client.get_role_mapping_policy(req.policy_id)
        elif req.policy_type == "enforcement":
            policy = client.get_enforcement_policy(req.policy_id)
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown policy_type '{req.policy_type}'. Expected 'role_mapping' or 'enforcement'.",
            )
        return ClearPassPolicyDetailResponse(policy=policy)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ClearPass") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ClearPass") from exc


@router.post("/clearpass/service-detail", response_model=ClearPassServiceDetailResponse)
def clearpass_service_detail(req: ClearPassServiceDetailRequest) -> ClearPassServiceDetailResponse:
    """Fetch full detail for a single ClearPass service (for template loading)."""
    try:
        client = ClearPassClient(
            req.server_url, req.client_id, req.client_secret, req.verify_ssl
        )
        service = client.get_service(req.service_id)
        return ClearPassServiceDetailResponse(service=service)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ClearPass") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ClearPass") from exc


# ---------------------------------------------------------------------------
# ISE endpoints
# ---------------------------------------------------------------------------


@router.post("/ise/connect", response_model=ConnectResponse)
def ise_connect(req: ISEConnectRequest) -> ConnectResponse:
    """Test ISE connectivity and return version info."""
    try:
        client = ISEClient(req.server_url, req.username, req.password, req.verify_ssl)
        version = client.test_connection()
        return ConnectResponse(success=True, platform="ise", version=version)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ISE") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ISE") from exc


@router.post("/ise/elements", response_model=ISEElementsResponse)
def ise_elements(req: ISEElementsRequest) -> ISEElementsResponse:
    """Fetch all policy elements from a live ISE instance."""
    try:
        client = ISEClient(req.server_url, req.username, req.password, req.verify_ssl)
        data = client.get_all_elements()
        return ISEElementsResponse(**data)
    except httpx.HTTPStatusError as exc:
        raise _handle_http_status(exc, "ISE") from exc
    except httpx.RequestError as exc:
        raise _handle_connect_error(exc, "ISE") from exc
