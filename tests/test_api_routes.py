"""Tests for API route boundary conditions.

Covers upload validation (size, type, malformed XML) and basic happy-path
responses for /api/services and /api/flow.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "Service.xml"
VALID_XML = FIXTURE.read_bytes()

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
