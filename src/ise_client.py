"""Cisco ISE API client.

Fetches policy elements from a live ISE instance using the ISE OpenAPI
(port 443, ISE 3.1+) for all resources.  HTTP Basic authentication.
Stateless: credentials are passed per-request; nothing is cached server-side.
"""
from __future__ import annotations

import base64
from urllib.parse import urlparse, urlunparse

import httpx

_OPENAPI_PORT = 443


class ISEClient:
    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._username = username
        self._password = password
        self._verify = verify_ssl

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(
            f"{self._username}:{self._password}".encode()
        ).decode()
        return {"Authorization": f"Basic {token}"}

    def _make_base(self, port: int) -> str:
        """Build a base URL for the given port, stripping any existing port."""
        parsed = urlparse(self._server_url)
        netloc = f"{parsed.hostname}:{port}"
        return urlunparse(parsed._replace(netloc=netloc, path=""))

    def _get_openapi(self, http: httpx.Client, path: str) -> list[dict]:
        """Fetch from ISE OpenAPI (port 443).

        ISE wraps responses in: {"version": "...", "response": [...]}
        """
        headers = {**self._auth_header(), "Accept": "application/json"}
        resp = http.get(
            f"{self._make_base(_OPENAPI_PORT)}{path}",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "response" in data:
            return list(data["response"])
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Element fetchers
    # ------------------------------------------------------------------

    def get_radius_policy_sets(self) -> list[dict]:
        with httpx.Client(verify=self._verify) as http:
            return self._get_openapi(http, "/api/v1/policy/network-access/policy-set")

    def get_tacacs_policy_sets(self) -> list[dict]:
        with httpx.Client(verify=self._verify) as http:
            return self._get_openapi(http, "/api/v1/policy/device-admin/policy-set")

    def get_profiles(self) -> list[dict]:
        with httpx.Client(verify=self._verify) as http:
            return self._get_openapi(http, "/api/v1/policy/network-access/authorization-profiles")

    def get_identity_stores(self) -> list[dict]:
        with httpx.Client(verify=self._verify) as http:
            return self._get_openapi(http, "/api/v1/policy/network-access/identity-stores")

    def test_connection(self) -> str:
        """Probe the OpenAPI endpoint. Returns a version string or 'ISE'."""
        with httpx.Client(verify=self._verify) as http:
            headers = {**self._auth_header(), "Accept": "application/json"}
            resp = http.get(
                f"{self._make_base(_OPENAPI_PORT)}/api/v1/policy/network-access/policy-set",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("version", "ISE"))

    # ------------------------------------------------------------------
    # Bulk fetch
    # ------------------------------------------------------------------

    def get_all_elements(self) -> dict:
        """Fetch all policy element types.

        Soft-fails individual resource types.  Returns a dict matching
        ISEElementsResponse schema.
        """
        result: dict = {
            "radius_policy_sets": [],
            "tacacs_policy_sets": [],
            "profiles": [],
            "identity_stores": [],
            "warnings": [],
        }

        fetchers: dict[str, str] = {
            "radius_policy_sets": "/api/v1/policy/network-access/policy-set",
            "tacacs_policy_sets": "/api/v1/policy/device-admin/policy-set",
            "profiles": "/api/v1/policy/network-access/authorization-profiles",
            "identity_stores": "/api/v1/policy/network-access/identity-stores",
        }

        with httpx.Client(verify=self._verify) as http:
            for key, path in fetchers.items():
                try:
                    result[key] = self._get_openapi(http, path)
                except Exception as exc:  # noqa: BLE001
                    result["warnings"].append(f"Failed to fetch {key}: {exc}")

        return result
