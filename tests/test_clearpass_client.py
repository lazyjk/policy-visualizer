"""Unit tests for src/clearpass_client.py.

All outbound HTTP calls are intercepted via unittest.mock so no live
ClearPass instance is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.clearpass_client import ClearPassClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN_RESPONSE = {"access_token": "test-token-123", "token_type": "Bearer", "expires_in": 3600}

_VERSION_RESPONSE = {
    "app_major_version": "6",
    "app_minor_version": "11",
    "app_service_release": "2",
}

_ROLE_PAGE = {
    "_embedded": {"items": [{"id": "r1", "name": "Employee"}, {"id": "r2", "name": "Contractor"}]},
    "total": 2,
}


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------

def test_get_token_posts_client_credentials():
    mock_resp = _mock_response(_TOKEN_RESPONSE)
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = mock_resp

    with patch("src.clearpass_client.httpx.Client", return_value=mock_http):
        client = ClearPassClient("https://cp.example.com", "my-id", "my-secret")
        token = client._get_token()

    assert token == "test-token-123"
    mock_http.post.assert_called_once()
    call_kwargs = mock_http.post.call_args
    assert "grant_type" in call_kwargs.kwargs.get("data", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})


def test_get_token_uses_correct_endpoint():
    mock_resp = _mock_response(_TOKEN_RESPONSE)
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = mock_resp

    with patch("src.clearpass_client.httpx.Client", return_value=mock_http):
        client = ClearPassClient("https://cp.example.com", "id", "secret")
        client._get_token()

    url = mock_http.post.call_args.args[0]
    assert url == "https://cp.example.com/api/oauth"


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_get_version_returns_dotted_string():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = _mock_response(_TOKEN_RESPONSE)
    mock_http.get.return_value = _mock_response(_VERSION_RESPONSE)

    with patch("src.clearpass_client.httpx.Client", return_value=mock_http):
        client = ClearPassClient("https://cp.example.com", "id", "secret")
        version = client.get_version()

    assert version == "6.11.2"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_get_pages_accumulates_multiple_pages():
    page1 = {
        "_embedded": {"items": [{"id": f"r{i}", "name": f"Role{i}"} for i in range(100)]},
        "total": 150,
    }
    page2 = {
        "_embedded": {"items": [{"id": f"r{i}", "name": f"Role{i}"} for i in range(100, 150)]},
        "total": 150,
    }
    mock_http = MagicMock()
    mock_http.get.side_effect = [_mock_response(page1), _mock_response(page2)]

    client = ClearPassClient("https://cp.example.com", "id", "secret")
    results = client._get_pages(mock_http, "tok", "/api/role")

    assert len(results) == 150
    assert mock_http.get.call_count == 2


def test_get_pages_stops_when_all_fetched():
    page = {
        "_embedded": {"items": [{"id": "r1", "name": "Role1"}]},
        "total": 1,
    }
    mock_http = MagicMock()
    mock_http.get.return_value = _mock_response(page)

    client = ClearPassClient("https://cp.example.com", "id", "secret")
    results = client._get_pages(mock_http, "tok", "/api/role")

    assert len(results) == 1
    assert mock_http.get.call_count == 1


# ---------------------------------------------------------------------------
# get_all_elements — soft-fail
# ---------------------------------------------------------------------------

def test_get_all_elements_soft_fails_on_partial_error():
    """If one resource type fails, others should still be returned."""
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = _mock_response(_TOKEN_RESPONSE)

    def get_side_effect(url: str, **_kwargs):
        if "/api/role" in url:
            raise Exception("Connection timeout")
        return _mock_response({"_embedded": {"items": []}, "total": 0})

    mock_http.get.side_effect = get_side_effect

    with patch("src.clearpass_client.httpx.Client", return_value=mock_http):
        client = ClearPassClient("https://cp.example.com", "id", "secret")
        result = client.get_all_elements()

    assert len(result["warnings"]) >= 1
    assert any("roles" in w for w in result["warnings"])
    # Other keys should still be present (empty lists)
    assert "services" in result
    assert isinstance(result["services"], list)


def test_get_all_elements_returns_all_keys():
    mock_http = MagicMock()
    mock_http.__enter__ = lambda s: mock_http
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post.return_value = _mock_response(_TOKEN_RESPONSE)
    mock_http.get.return_value = _mock_response({"_embedded": {"items": []}, "total": 0})

    with patch("src.clearpass_client.httpx.Client", return_value=mock_http):
        client = ClearPassClient("https://cp.example.com", "id", "secret")
        result = client.get_all_elements()

    expected_keys = {
        "services", "roles", "enforcement_profiles", "enforcement_policies",
        "role_mapping_policies", "auth_methods", "auth_sources", "warnings",
    }
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

        def post(self, *a, **kw):
            return _mock_response(_TOKEN_RESPONSE)

        def get(self, *a, **kw):
            return _mock_response({"_embedded": {"items": []}, "total": 0})

    with patch("src.clearpass_client.httpx.Client", FakeClient):
        client = ClearPassClient("https://cp.example.com", "id", "secret", verify_ssl=False)
        client.get_roles()

    assert captured.get("verify") is False
