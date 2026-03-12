"""Tests for API route boundary conditions.

Covers upload validation (size, type, malformed XML) and basic happy-path
responses for /api/services and /api/flow.  Includes ISE format cases.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"
VALID_XML = FIXTURE.read_bytes()

ISE_FIXTURE = Path(__file__).parent / "fixtures" / "ISEPolicyConfig.xml"
ISE_XML = ISE_FIXTURE.read_bytes()

RADIUS_PROXY_FIXTURE = Path(__file__).parent / "fixtures" / "radius-proxy.xml"
RADIUS_PROXY_XML = RADIUS_PROXY_FIXTURE.read_bytes()

# Minimal well-formed XML with the ClearPass namespace but no services.
EMPTY_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<TipsContents xmlns="http://www.avendasys.com/tipsapiDefs/1.0"></TipsContents>'
)

MALFORMED_XML = b"<not valid xml <><>"

client = TestClient(app)


def _post(path: str, filename: str, data: bytes, content_type: str = "application/xml"):
    return client.post(
        path,
        files={"file": (filename, io.BytesIO(data), content_type)},
    )


# ---------------------------------------------------------------------------
# /api/services
# ---------------------------------------------------------------------------

def test_services_valid_xml_returns_200():
    res = _post("/api/services", "Service.xml", VALID_XML)
    assert res.status_code == 200
    body = res.json()
    assert "services" in body
    assert len(body["services"]) >= 1


def test_services_response_includes_service_type():
    res = _post("/api/services", "Service.xml", VALID_XML)
    assert res.status_code == 200
    svc = res.json()["services"][0]
    assert "service_type" in svc


def test_services_non_xml_extension_returns_415():
    res = _post("/api/services", "document.pdf", VALID_XML)
    assert res.status_code == 415


def test_services_malformed_xml_returns_422():
    res = _post("/api/services", "bad.xml", MALFORMED_XML)
    assert res.status_code == 422
    # Must not expose a raw stack trace in the detail field
    detail = res.json().get("detail", "")
    assert "traceback" not in detail.lower()
    assert "Traceback" not in detail


def test_services_empty_xml_returns_422():
    res = _post("/api/services", "empty.xml", EMPTY_XML)
    assert res.status_code == 422


def test_services_oversized_returns_413():
    # Construct data slightly over the 10 MB limit
    big = b"<r/>" + b"x" * (10 * 1024 * 1024)
    res = _post("/api/services", "big.xml", big)
    assert res.status_code == 413


def test_services_no_file_returns_422():
    res = client.post("/api/services")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# /api/flow
# ---------------------------------------------------------------------------

def test_flow_valid_xml_returns_200():
    res = _post("/api/flow", "Service.xml", VALID_XML)
    assert res.status_code == 200
    body = res.json()
    assert "nodes" in body
    assert "edges" in body


def test_flow_response_includes_service_type():
    res = _post("/api/flow", "Service.xml", VALID_XML)
    assert res.status_code == 200
    assert "service_type" in res.json()


def test_flow_non_xml_extension_returns_415():
    res = _post("/api/flow", "data.csv", VALID_XML)
    assert res.status_code == 415


def test_flow_malformed_xml_returns_422():
    res = _post("/api/flow", "bad.xml", MALFORMED_XML)
    assert res.status_code == 422
    detail = res.json().get("detail", "")
    assert "traceback" not in detail.lower()


def test_flow_oversized_returns_413():
    big = b"<r/>" + b"x" * (10 * 1024 * 1024)
    res = _post("/api/flow", "big.xml", big)
    assert res.status_code == 413


def test_flow_unknown_service_returns_404():
    res = client.post(
        "/api/flow?service=DoesNotExist",
        files={"file": ("Service.xml", io.BytesIO(VALID_XML), "application/xml")},
    )
    assert res.status_code == 404


def test_flow_no_file_returns_422():
    res = client.post("/api/flow")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# ISE format — /api/services
# ---------------------------------------------------------------------------

def test_ise_services_returns_200():
    res = _post("/api/services", "ISEPolicyConfig.xml", ISE_XML)
    assert res.status_code == 200
    body = res.json()
    assert "services" in body
    assert len(body["services"]) == 3   # 2 RADIUS + 1 TACACS


def test_ise_services_includes_radius_and_tacacs():
    res = _post("/api/services", "ISEPolicyConfig.xml", ISE_XML)
    types = {s["service_type"] for s in res.json()["services"]}
    assert "RADIUS" in types
    assert "TACACS" in types


def test_ise_services_policy_set_names():
    res = _post("/api/services", "ISEPolicyConfig.xml", ISE_XML)
    names = {s["name"] for s in res.json()["services"]}
    assert "Test-DOT1X" in names
    assert "Default" in names


# ---------------------------------------------------------------------------
# ISE format — /api/flow
# ---------------------------------------------------------------------------

def test_ise_flow_default_returns_200():
    """No service param → first policy set is compiled."""
    res = _post("/api/flow", "ISEPolicyConfig.xml", ISE_XML)
    assert res.status_code == 200
    body = res.json()
    assert "nodes" in body
    assert "edges" in body


def test_ise_flow_by_id():
    # Use the stable UUID for the Test-DOT1X policy set (RADIUS)
    res = client.post(
        "/api/flow?service=036041df-807c-4adf-a68c-4824a4849916",
        files={"file": ("ISEPolicyConfig.xml", io.BytesIO(ISE_XML), "application/xml")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["service_name"] == "Test-DOT1X"


def test_ise_flow_unknown_policy_set_returns_404():
    res = client.post(
        "/api/flow?service=NoSuchSet",
        files={"file": ("ISEPolicyConfig.xml", io.BytesIO(ISE_XML), "application/xml")},
    )
    assert res.status_code == 404


def test_ise_flow_response_has_service_type():
    res = _post("/api/flow", "ISEPolicyConfig.xml", ISE_XML)
    body = res.json()
    assert body["service_type"] in ("RADIUS", "TACACS")


# ---------------------------------------------------------------------------
# Radius Proxy
# ---------------------------------------------------------------------------

def test_radius_proxy_services_response():
    res = _post("/api/services", "radius-proxy.xml", RADIUS_PROXY_XML)
    assert res.status_code == 200
    services = res.json()["services"]
    assert any(s["service_type"] == "RADIUS_PROXY" for s in services)


def test_radius_proxy_flow_response():
    res = _post("/api/flow", "radius-proxy.xml", RADIUS_PROXY_XML)
    assert res.status_code == 200
    body = res.json()
    assert body["service_type"] == "RADIUS_PROXY"


# ---------------------------------------------------------------------------
# include_details flag — backward compatibility and details payload
# ---------------------------------------------------------------------------

def test_flow_default_details_is_null():
    """Without include_details, details field is null (backward-compatible)."""
    res = _post("/api/flow", "Service.xml", VALID_XML)
    assert res.status_code == 200
    assert res.json().get("details") is None


def test_flow_include_details_false_is_null():
    """Explicit include_details=false is the same as the default."""
    res = client.post(
        "/api/flow?include_details=false",
        files={"file": ("Service.xml", io.BytesIO(VALID_XML), "application/xml")},
    )
    assert res.status_code == 200
    assert res.json().get("details") is None


def test_flow_include_details_clearpass():
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("Service.xml", io.BytesIO(VALID_XML), "application/xml")},
    )
    assert res.status_code == 200
    details = res.json()["details"]
    assert details is not None
    assert "service_context" in details
    assert "rule_index" in details
    assert isinstance(details["enforcement_rules"], list)
    assert isinstance(details["role_mapping_rules"], list)
    assert details["authen_rules"] == []


def test_flow_include_details_ise():
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("ISEPolicyConfig.xml", io.BytesIO(ISE_XML), "application/xml")},
    )
    assert res.status_code == 200
    details = res.json()["details"]
    assert details is not None
    assert isinstance(details["authen_rules"], list)
    assert len(details["authen_rules"]) > 0
    assert details["role_mapping_rules"] == []


def test_flow_details_rule_index_subset_of_trace_ids():
    """All rule_index keys must appear as trace_rule_id on at least one node."""
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("Service.xml", io.BytesIO(VALID_XML), "application/xml")},
    )
    body = res.json()
    trace_ids = {n["trace_rule_id"] for n in body["nodes"] if n["trace_rule_id"]}
    rule_index_keys = set(body["details"]["rule_index"].keys())
    assert rule_index_keys.issubset(trace_ids)


def test_flow_details_enforcement_rules_ordered():
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("Service.xml", io.BytesIO(VALID_XML), "application/xml")},
    )
    rules = res.json()["details"]["enforcement_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_flow_details_ise_authen_rules_ordered():
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("ISEPolicyConfig.xml", io.BytesIO(ISE_XML), "application/xml")},
    )
    rules = res.json()["details"]["authen_rules"]
    if rules:
        indices = [r["index"] for r in rules]
        assert indices == sorted(indices)


def test_flow_details_radius_proxy():
    """RADIUS_PROXY may have no role mapping rules, but payload must still be present."""
    res = client.post(
        "/api/flow?include_details=true",
        files={"file": ("radius-proxy.xml", io.BytesIO(RADIUS_PROXY_XML), "application/xml")},
    )
    assert res.status_code == 200
    assert res.json()["details"] is not None
