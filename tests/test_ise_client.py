"""Unit tests for src/ise_client.py.

All outbound HTTP calls are intercepted via unittest.mock so no live
ISE instance is required.
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from src.ise_client import ISEClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPENAPI_POLICY_SETS = {
    "version": "1.0.0",
    "response": [
        {"id": "ps1", "name": "Corp Wireless", "rank": 1},
        {"id": "ps2", "name": "Guest Wireless", "rank": 2},
    ],
}

_OPENAPI_EMPTY = {"version": "1.0.0", "response": []}


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------

def test_auth_header_is_basic_base64():
    client = ISEClient("https://ise.example.com", "admin", "S3cr3t!")
    header = client._auth_header()
    expected = base64.b64encode(b"admin:S3cr3t!").decode()
    assert header["Authorization"] == f"Basic {expected}"


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def test_make_base_openapi_port():
    client = ISEClient("https://ise.example.com", "admin", "pass")
    base = client._make_base(443)
    assert ":443" in base
    assert "ise.example.com" in base


def test_make_base_strips_existing_port():
    client = ISEClient("https://ise.example.com:9070", "admin", "pass")
    base = client._make_base(443)
    assert ":443" in base
    assert ":9070" not in base


# ---------------------------------------------------------------------------
# OpenAPI response envelope unwrapping
# ---------------------------------------------------------------------------

def test_get_openapi_unwraps_response_envelope():
    mock_http = MagicMock()
    mock_http.get.return_value = _mock_response(_OPENAPI_POLICY_SETS)

    client = ISEClient("https://ise.example.com", "admin", "pass")
    result = client._get_openapi(mock_http, "/api/v1/policy/network-access/policy-set")

    assert len(result) == 2
    assert result[0]["name"] == "Corp Wireless"


def test_get_openapi_returns_list_if_no_envelope():
    raw_list = [{"id": "x", "name": "Something"}]
    mock_http = MagicMock()
    mock_http.get.return_value = _mock_response(raw_list)  # type: ignore[arg-type]

    client = ISEClient("https://ise.example.com", "admin", "pass")
    mock_http.get.return_value.json.return_value = raw_list
    result = client._get_openapi(mock_http, "/api/v1/policy/network-access/policy-set")

    assert result == raw_list


# ---------------------------------------------------------------------------
# get_profiles / get_identity_stores use OpenAPI paths
# ---------------------------------------------------------------------------

def test_get_profiles_calls_openapi_path():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = _mock_response({"version": "1.0.0", "response": [{"name": "PermitAccess"}]})

    with patch("src.ise_client.httpx.Client", return_value=mock_http):
        client = ISEClient("https://ise.example.com", "admin", "pass")
        result = client.get_profiles()

    assert result == [{"name": "PermitAccess"}]
    call_url = mock_http.get.call_args[0][0]
    assert "/api/v1/policy/network-access/authorization-profiles" in call_url


def test_get_identity_stores_calls_openapi_path():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = _mock_response({"version": "1.0.0", "response": [{"name": "Internal Users"}]})

    with patch("src.ise_client.httpx.Client", return_value=mock_http):
        client = ISEClient("https://ise.example.com", "admin", "pass")
        result = client.get_identity_stores()

    assert result == [{"name": "Internal Users"}]
    call_url = mock_http.get.call_args[0][0]
    assert "/api/v1/policy/network-access/identity-stores" in call_url


# ---------------------------------------------------------------------------
# get_all_elements — soft-fail
# ---------------------------------------------------------------------------

def test_get_all_elements_soft_fails_on_partial_error():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)

    def get_side_effect(url: str, **_kwargs):
        if "network-access/policy-set" in url:
            raise Exception("Timeout")
        return _mock_response(_OPENAPI_EMPTY)

    mock_http.get.side_effect = get_side_effect

    with patch("src.ise_client.httpx.Client", return_value=mock_http):
        client = ISEClient("https://ise.example.com", "admin", "pass")
        result = client.get_all_elements()

    assert any("radius_policy_sets" in w for w in result["warnings"])
    assert "tacacs_policy_sets" in result
    assert isinstance(result["profiles"], list)


def test_get_all_elements_returns_all_keys():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = _mock_response({"version": "1.0.0", "response": []})

    with patch("src.ise_client.httpx.Client", return_value=mock_http):
        client = ISEClient("https://ise.example.com", "admin", "pass")
        result = client.get_all_elements()

    expected_keys = {"radius_policy_sets", "tacacs_policy_sets", "profiles", "identity_stores", "warnings"}
    assert expected_keys == set(result.keys())


# ---------------------------------------------------------------------------
# SSL verify flag
# ---------------------------------------------------------------------------

def test_verify_ssl_false_passed_to_httpx():
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self): return self
        def __exit__(self, *a): return False

        def get(self, *a, **kw):
            return _mock_response({"version": "1.0.0", "response": []})

    with patch("src.ise_client.httpx.Client", FakeClient):
        client = ISEClient("https://ise.example.com", "admin", "pass", verify_ssl=False)
        client.get_radius_policy_sets()

    assert captured.get("verify") is False
