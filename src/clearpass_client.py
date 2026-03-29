"""ClearPass REST API client.

Fetches policy elements from a live ClearPass instance via OAuth2
client-credentials. Stateless: a fresh token is fetched per top-level
operation; nothing is cached server-side.
"""
from __future__ import annotations

import httpx

_PAGE_SIZE = 100


class ClearPassClient:
    def __init__(
        self,
        server_url: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
    ) -> None:
        self._base = server_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._verify = verify_ssl

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        with httpx.Client(verify=self._verify) as http:
            resp = http.post(
                f"{self._base}/api/oauth",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["access_token"])

    # ------------------------------------------------------------------
    # Internal fetch helpers
    # ------------------------------------------------------------------

    def _get_pages(self, http: httpx.Client, token: str, path: str) -> list[dict]:
        """Paginate through a ClearPass HAL collection and return all items."""
        headers = {"Authorization": f"Bearer {token}"}
        results: list[dict] = []
        offset = 0
        while True:
            resp = http.get(
                f"{self._base}{path}",
                params={"offset": offset, "limit": _PAGE_SIZE},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            # ClearPass uses HAL: {"_embedded": {"items": [...]}, "total": N}
            items: list[dict] = data.get("_embedded", {}).get("items", [])
            results.extend(items)
            total: int = data.get("total", len(items))
            offset += len(items)
            if not items or offset >= total:
                break
        return results

    def get_version(self) -> str:
        token = self._get_token()
        with httpx.Client(verify=self._verify) as http:
            resp = http.get(
                f"{self._base}/api/server/version",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            major = data.get("app_major_version", "")
            minor = data.get("app_minor_version", "")
            patch = data.get("app_service_release", "")
            return f"{major}.{minor}.{patch}".strip(".")

    # ------------------------------------------------------------------
    # Element fetchers (each uses a single shared token + HTTP client)
    # ------------------------------------------------------------------

    def _fetch(self, path: str) -> list[dict]:
        token = self._get_token()
        with httpx.Client(verify=self._verify) as http:
            return self._get_pages(http, token, path)

    def get_roles(self) -> list[dict]:
        return self._fetch("/api/role")

    def get_enforcement_profiles(self) -> list[dict]:
        return self._fetch("/api/enforcement-profile")

    def get_enforcement_policies(self) -> list[dict]:
        return self._fetch("/api/enforcement-policy")

    def get_role_mapping_policies(self) -> list[dict]:
        return self._fetch("/api/role-mapping")

    def get_auth_methods(self) -> list[dict]:
        return self._fetch("/api/auth-method")

    def get_auth_sources(self) -> list[dict]:
        return self._fetch("/api/auth-source")

    def get_services(self) -> list[dict]:
        return self._fetch("/api/config/service")

    # ------------------------------------------------------------------
    # Single-item fetchers (for template loading)
    # ------------------------------------------------------------------

    def _get_item(self, path: str) -> dict:
        token = self._get_token()
        with httpx.Client(verify=self._verify) as http:
            resp = http.get(
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return dict(resp.json())

    def get_service(self, service_id: str) -> dict:
        return self._get_item(f"/api/config/service/{service_id}")

    def get_role_mapping_policy(self, policy_id: str) -> dict:
        return self._get_item(f"/api/role-mapping/{policy_id}")

    def get_enforcement_policy(self, policy_id: str) -> dict:
        return self._get_item(f"/api/enforcement-policy/{policy_id}")

    # ------------------------------------------------------------------
    # Dictionary fetchers (for condition builder attribute lists)
    # ------------------------------------------------------------------

    def get_attributes(self) -> dict:
        """Fetch condition attribute dictionaries from ClearPass.

        Merges results from four sources:
          /api/radius-dictionary         — RADIUS VSA namespaces + attributes
          /api/application-dictionary    — ClearPass application attributes
                                           (name field is "Namespace:Attribute")
          /api/tacacs-service-dictionary — TACACS+ attributes
          /api/auth-source               — generates "Authorization:{name}" namespace
                                           entries for each configured auth source

        Returns {"namespaces": {namespace: [attr, ...]}, "warnings": [...]}.
        Each endpoint is soft-failed; partial results are returned with warnings.
        """
        namespaces: dict[str, list[str]] = {}
        warnings: list[str] = []
        token = self._get_token()

        endpoints = [
            ("/api/radius-dictionary", "radius"),
            ("/api/application-dictionary", "application"),
            ("/api/tacacs-service-dictionary", "tacacs"),
        ]

        with httpx.Client(verify=self._verify) as http:
            for path, label in endpoints:
                try:
                    items = self._get_pages(http, token, path)
                    for item in items:
                        if label == "radius":
                            # RADIUS dictionary: each item is one vendor entry.
                            # vendor_name already carries the "Radius:" prefix (e.g. "Radius:Aruba").
                            # Individual VSA attribute names are in the nested "attributes" list.
                            ns = str(item.get("vendor_name") or "")
                            if not ns:
                                continue
                            namespaces.setdefault(ns, [])
                            for attr_entry in item.get("attributes", []):
                                attr = str(attr_entry.get("attr_name") or "")
                                if attr and attr not in namespaces[ns]:
                                    namespaces[ns].append(attr)
                        else:
                            # Application / TACACS dictionaries — flat item structure.
                            vendor_ns = str(item.get("vendor_name") or item.get("namespace") or "")
                            attr_name = str(item.get("attribute_name") or "")
                            full_name = str(item.get("name") or "")

                            if vendor_ns:
                                ns = vendor_ns
                                attr = attr_name or full_name
                            elif ":" in full_name:
                                ns, attr = full_name.split(":", 1)
                            else:
                                ns = label
                                attr = full_name

                            if attr:
                                namespaces.setdefault(ns, [])
                                if attr not in namespaces[ns]:
                                    namespaces[ns].append(attr)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"Failed to fetch {label} dictionary: {exc}")

            # Auth sources → "Authorization:{name}" namespace entries.
            # ClearPass role-mapping conditions use "Authorization:{sourceName}"
            # as the namespace for identity-source attributes.
            try:
                sources = self._get_pages(http, token, "/api/auth-source")
                for src in sources:
                    src_name = str(src.get("name") or "")
                    if src_name:
                        namespaces.setdefault(f"Authorization:{src_name}", [])
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Failed to fetch auth sources: {exc}")

        return {"namespaces": namespaces, "warnings": warnings}

    # ------------------------------------------------------------------
    # Bulk fetch — single token for all resource types
    # ------------------------------------------------------------------

    def get_all_elements(self) -> dict:
        """Fetch all policy element types.

        Soft-fails individual resource types: if one fetch fails, a warning
        is added and the rest continue.  Returns a dict matching
        ClearPassElementsResponse schema.
        """
        result: dict = {
            "services": [],
            "roles": [],
            "enforcement_profiles": [],
            "enforcement_policies": [],
            "role_mapping_policies": [],
            "auth_methods": [],
            "auth_sources": [],
            "warnings": [],
        }

        token = self._get_token()

        fetchers: dict[str, str] = {
            "services": "/api/config/service",
            "roles": "/api/role",
            "enforcement_profiles": "/api/enforcement-profile",
            "enforcement_policies": "/api/enforcement-policy",
            "role_mapping_policies": "/api/role-mapping",
            "auth_methods": "/api/auth-method",
            "auth_sources": "/api/auth-source",
        }

        with httpx.Client(verify=self._verify) as http:
            for key, path in fetchers.items():
                try:
                    result[key] = self._get_pages(http, token, path)
                except Exception as exc:  # noqa: BLE001
                    result["warnings"].append(f"Failed to fetch {key}: {exc}")

        return result
