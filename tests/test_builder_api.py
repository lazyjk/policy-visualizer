"""Tests for the Policy Builder API routes (/api/builder/*).

ClearPassClient and ISEClient are patched so no live platform is needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CP_CREDS = {
    "server_url": "https://cp.example.com",
    "client_id": "my-client",
    "client_secret": "my-secret",
    "verify_ssl": True,
}

_ISE_CREDS = {
    "server_url": "https://ise.example.com",
    "username": "admin",
    "password": "Password1",
    "verify_ssl": True,
}

_CP_ELEMENTS = {
    "services": [{"id": "s1", "name": "Corp WiFi"}],
    "roles": [{"id": "r1", "name": "Employee"}],
    "enforcement_profiles": [],
    "enforcement_policies": [],
    "role_mapping_policies": [],
    "auth_methods": [],
    "auth_sources": [],
    "warnings": [],
}

_ISE_ELEMENTS = {
    "radius_policy_sets": [{"id": "ps1", "name": "Wireless"}],
    "tacacs_policy_sets": [],
    "profiles": [{"id": "p1", "name": "PermitAccess"}],
    "identity_stores": [],
    "warnings": [],
}


def _mock_cp_client(version: str = "6.11.2", elements: dict | None = None) -> MagicMock:
    m = MagicMock()
    m.get_version.return_value = version
    m.get_all_elements.return_value = elements or _CP_ELEMENTS
    return m


def _mock_ise_client(version: str = "1.0.0", elements: dict | None = None) -> MagicMock:
    m = MagicMock()
    m.test_connection.return_value = version
    m.get_all_elements.return_value = elements or _ISE_ELEMENTS
    return m


# ---------------------------------------------------------------------------
# ClearPass /connect
# ---------------------------------------------------------------------------

def test_clearpass_connect_success():
    with patch("api.routes.builder.ClearPassClient", return_value=_mock_cp_client()):
        res = client.post("/api/builder/clearpass/connect", json=_CP_CREDS)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["platform"] == "clearpass"
    assert body["version"] == "6.11.2"


def test_clearpass_connect_401_on_bad_credentials():
    mock = MagicMock()
    mock.get_version.side_effect = httpx.HTTPStatusError(
        "Unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )
    with patch("api.routes.builder.ClearPassClient", return_value=mock):
        res = client.post("/api/builder/clearpass/connect", json=_CP_CREDS)
    assert res.status_code == 401


def test_clearpass_connect_502_when_unreachable():
    mock = MagicMock()
    mock.get_version.side_effect = httpx.ConnectError("Connection refused")
    with patch("api.routes.builder.ClearPassClient", return_value=mock):
        res = client.post("/api/builder/clearpass/connect", json=_CP_CREDS)
    assert res.status_code == 502


# ---------------------------------------------------------------------------
# ClearPass /elements
# ---------------------------------------------------------------------------

def test_clearpass_elements_returns_all_keys():
    with patch("api.routes.builder.ClearPassClient", return_value=_mock_cp_client()):
        res = client.post("/api/builder/clearpass/elements", json=_CP_CREDS)
    assert res.status_code == 200
    body = res.json()
    for key in ("services", "roles", "enforcement_profiles", "enforcement_policies",
                "role_mapping_policies", "auth_methods", "auth_sources", "warnings"):
        assert key in body


def test_clearpass_elements_propagates_service_data():
    with patch("api.routes.builder.ClearPassClient", return_value=_mock_cp_client()):
        res = client.post("/api/builder/clearpass/elements", json=_CP_CREDS)
    body = res.json()
    assert body["services"][0]["name"] == "Corp WiFi"


def test_clearpass_elements_401_on_bad_credentials():
    mock = MagicMock()
    mock.get_all_elements.side_effect = httpx.HTTPStatusError(
        "Forbidden",
        request=MagicMock(),
        response=MagicMock(status_code=403),
    )
    with patch("api.routes.builder.ClearPassClient", return_value=mock):
        res = client.post("/api/builder/clearpass/elements", json=_CP_CREDS)
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# ISE /connect
# ---------------------------------------------------------------------------

def test_ise_connect_success():
    with patch("api.routes.builder.ISEClient", return_value=_mock_ise_client()):
        res = client.post("/api/builder/ise/connect", json=_ISE_CREDS)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["platform"] == "ise"


def test_ise_connect_401_on_bad_credentials():
    mock = MagicMock()
    mock.test_connection.side_effect = httpx.HTTPStatusError(
        "Unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )
    with patch("api.routes.builder.ISEClient", return_value=mock):
        res = client.post("/api/builder/ise/connect", json=_ISE_CREDS)
    assert res.status_code == 401


def test_ise_connect_502_when_unreachable():
    mock = MagicMock()
    mock.test_connection.side_effect = httpx.ConnectError("No route to host")
    with patch("api.routes.builder.ISEClient", return_value=mock):
        res = client.post("/api/builder/ise/connect", json=_ISE_CREDS)
    assert res.status_code == 502


# ---------------------------------------------------------------------------
# ISE /elements
# ---------------------------------------------------------------------------

def test_ise_elements_returns_all_keys():
    with patch("api.routes.builder.ISEClient", return_value=_mock_ise_client()):
        res = client.post("/api/builder/ise/elements", json=_ISE_CREDS)
    assert res.status_code == 200
    body = res.json()
    for key in ("radius_policy_sets", "tacacs_policy_sets", "profiles", "identity_stores", "warnings"):
        assert key in body


def test_ise_elements_propagates_policy_set_data():
    with patch("api.routes.builder.ISEClient", return_value=_mock_ise_client()):
        res = client.post("/api/builder/ise/elements", json=_ISE_CREDS)
    body = res.json()
    assert body["radius_policy_sets"][0]["name"] == "Wireless"


def test_ise_elements_502_when_unreachable():
    mock = MagicMock()
    mock.get_all_elements.side_effect = httpx.ConnectError("Timeout")
    with patch("api.routes.builder.ISEClient", return_value=mock):
        res = client.post("/api/builder/ise/elements", json=_ISE_CREDS)
    assert res.status_code == 502


# ---------------------------------------------------------------------------
# Existing visualizer routes still work
# ---------------------------------------------------------------------------

def test_health_still_returns_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
