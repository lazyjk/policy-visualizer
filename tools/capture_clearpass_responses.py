#!/usr/bin/env python3
"""
Capture ClearPass API response schemas (field names + types only).

Connects to a live ClearPass instance, fetches one page from each
collection endpoint and the full detail for one sample item from each
single-item endpoint, then writes FIELD NAMES + INFERRED TYPES ONLY
(no actual values) to tests/fixtures/clearpass_api/<slug>.json.

These schema files are safe to run against production and commit to the
repo: they describe the API wire format without exposing policy content.

Usage:
    python tools/capture_clearpass_responses.py \\
        --url https://cppm.example.com \\
        --client-id MY_CLIENT_ID \\
        --client-secret MY_CLIENT_SECRET \\
        [--no-verify-ssl] \\
        [--output-dir tests/fixtures/clearpass_api]

Re-running overwrites existing files.  Run after a ClearPass upgrade to
pick up any new or changed fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

_PAGE_SIZE = 100
_MAX_DEPTH = 3  # how deep to recurse into nested objects/arrays


# ---------------------------------------------------------------------------
# Schema inference — no values, only field names + types
# ---------------------------------------------------------------------------


def _infer_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _schema_of(obj: dict, depth: int = 0) -> dict[str, Any]:
    """Recursively extract field names + types (values stripped)."""
    result: dict[str, Any] = {}
    for key, val in sorted(obj.items()):
        if isinstance(val, dict) and depth < _MAX_DEPTH:
            inner = _schema_of(val, depth + 1)
            result[key] = {"_type": "object", "_fields": inner} if inner else "object"
        elif isinstance(val, list):
            if not val:
                result[key] = "array"
            elif isinstance(val[0], dict) and depth < _MAX_DEPTH:
                merged = _merge_schemas(val, depth + 1)
                result[key] = {"_type": "array", "_item_fields": merged}
            else:
                result[key] = {"_type": "array", "_item_type": _infer_type(val[0])}
        else:
            result[key] = _infer_type(val)
    return result


def _merge_schemas(items: list[Any], depth: int = 0) -> dict[str, Any]:
    """Merge field schemas across all items (union — catches optional fields)."""
    merged: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, val in item.items():
            if key in merged:
                continue  # already recorded
            if isinstance(val, dict) and depth < _MAX_DEPTH:
                inner = _schema_of(val, depth + 1)
                merged[key] = {"_type": "object", "_fields": inner} if inner else "object"
            elif isinstance(val, list):
                if not val:
                    merged[key] = "array"
                elif isinstance(val[0], dict) and depth < _MAX_DEPTH:
                    merged[key] = {
                        "_type": "array",
                        "_item_fields": _merge_schemas(val, depth + 1),
                    }
                else:
                    merged[key] = {"_type": "array", "_item_type": _infer_type(val[0])}
            else:
                merged[key] = _infer_type(val)
    return dict(sorted(merged.items()))


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_token(base: str, client_id: str, client_secret: str, verify: bool) -> str:
    with httpx.Client(verify=verify) as http:
        resp = http.post(
            f"{base}/api/oauth",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])


def _get_page(
    base: str,
    path: str,
    token: str,
    verify: bool,
    offset: int = 0,
    limit: int = _PAGE_SIZE,
) -> dict:
    with httpx.Client(verify=verify) as http:
        resp = http.get(
            f"{base}{path}",
            params={"offset": offset, "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return dict(resp.json())


def _get_item(base: str, path: str, token: str, verify: bool) -> dict:
    with httpx.Client(verify=verify) as http:
        resp = http.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return dict(resp.json())


# ---------------------------------------------------------------------------
# Capture functions — return schema dicts safe for commit
# ---------------------------------------------------------------------------


def capture_version(base: str, token: str, verify: bool) -> dict:
    data = _get_item(base, "/api/server/version", token, verify)
    return {
        "_endpoint": "GET /api/server/version",
        "_description": "ClearPass server version string",
        "response_type": "object",
        "fields": _schema_of(data),
    }


def capture_collection(
    base: str,
    path: str,
    token: str,
    verify: bool,
    description: str,
) -> tuple[dict, list[dict]]:
    """Return (schema_dict, raw_items) for a HAL collection endpoint."""
    data = _get_page(base, path, token, verify)
    items: list[dict] = data.get("_embedded", {}).get("items", [])
    total: int = data.get("total", len(items))

    # Describe the HAL envelope fields (minus _embedded which we handle separately)
    envelope_fields = _schema_of({k: v for k, v in data.items() if k != "_embedded"})

    schema = {
        "_endpoint": f"GET {path}",
        "_description": description,
        "response_type": "hal_collection",
        "hal_envelope_fields": envelope_fields,
        "total_items": total,
        "page_size_fetched": len(items),
        "item_fields": _merge_schemas(items),
    }
    return schema, items


def capture_single_item(
    base: str,
    path_template: str,
    item_id: str,
    token: str,
    verify: bool,
    description: str,
) -> dict:
    """Return schema dict for a single-item detail endpoint."""
    path = path_template.replace("{id}", item_id)
    data = _get_item(base, path, token, verify)
    return {
        "_endpoint": f"GET {path_template}",
        "_description": description,
        "response_type": "object",
        "fields": _schema_of(data),
    }


# ---------------------------------------------------------------------------
# Write helper
# ---------------------------------------------------------------------------


def _write(out_dir: Path, slug: str, schema: dict) -> None:
    path = out_dir / f"{slug}.json"
    path.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"    → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--url", required=True, help="ClearPass base URL")
    ap.add_argument("--client-id", required=True, dest="client_id")
    ap.add_argument("--client-secret", required=True, dest="client_secret")
    ap.add_argument(
        "--no-verify-ssl",
        action="store_true",
        dest="no_verify_ssl",
        help="Skip SSL certificate verification",
    )
    ap.add_argument(
        "--output-dir",
        default="tests/fixtures/clearpass_api",
        dest="output_dir",
        help="Output directory (default: tests/fixtures/clearpass_api)",
    )
    args = ap.parse_args()

    base = args.url.rstrip("/")
    verify = not args.no_verify_ssl
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Authenticating against {base} ...")
    try:
        token = _get_token(base, args.client_id, args.client_secret, verify)
    except Exception as exc:
        print(f"ERROR: authentication failed: {exc}", file=sys.stderr)
        return 1
    print("OK\n")

    errors: list[str] = []

    # --- server version ---
    print("server/version:")
    try:
        schema = capture_version(base, token, verify)
        _write(out_dir, "version", schema)
    except Exception as exc:
        msg = f"  WARN version: {exc}"
        print(msg)
        errors.append(msg)

    # --- collection endpoints ---
    # (path, slug, description)
    collections: list[tuple[str, str, str]] = [
        ("/api/config/service",          "services_page",             "ClearPass services list"),
        ("/api/role",                    "roles_page",                "ClearPass roles list"),
        ("/api/enforcement-profile",     "enforcement_profiles_page", "Enforcement profiles list"),
        ("/api/enforcement-policy",      "enforcement_policies_page", "Enforcement policies list"),
        ("/api/role-mapping",            "role_mappings_page",        "Role mapping policies list"),
        ("/api/auth-method",             "auth_methods_page",         "Authentication methods list"),
        ("/api/auth-source",             "auth_sources_page",         "Authentication sources list"),
        ("/api/radius-dictionary",       "radius_dict_page",          "RADIUS VSA dictionary"),
        ("/api/application-dictionary",  "app_dict_page",             "Application attribute dictionary"),
        ("/api/tacacs-service-dictionary","tacacs_dict_page",         "TACACS+ service dictionary"),
    ]

    # Map from collection path → first item id (for single-item captures)
    first_ids: dict[str, str] = {}

    for path, slug, desc in collections:
        print(f"{path}:")
        try:
            schema, items = capture_collection(base, path, token, verify, desc)
            _write(out_dir, slug, schema)
            print(f"    total_items={schema['total_items']}, page_fetched={schema['page_size_fetched']}")
            if items and isinstance(items[0], dict) and "id" in items[0]:
                first_ids[path] = str(items[0]["id"])
        except Exception as exc:
            msg = f"  WARN {path}: {exc}"
            print(msg)
            errors.append(msg)

    # --- single-item endpoints ---
    # (collection_path, path_template, slug, description)
    single_items: list[tuple[str, str, str, str]] = [
        (
            "/api/config/service",
            "/api/config/service/{id}",
            "service_item",
            "Single ClearPass service (full detail)",
        ),
        (
            "/api/role-mapping",
            "/api/role-mapping/{id}",
            "rm_item",
            "Single role mapping policy (full detail with rules)",
        ),
        (
            "/api/enforcement-policy",
            "/api/enforcement-policy/{id}",
            "enfpol_item",
            "Single enforcement policy (full detail with rules)",
        ),
    ]

    for collection_path, path_template, slug, desc in single_items:
        item_id = first_ids.get(collection_path)
        if not item_id:
            print(f"{path_template}: SKIP (no item id available from collection)")
            continue
        print(f"{path_template}:")
        try:
            schema = capture_single_item(base, path_template, item_id, token, verify, desc)
            _write(out_dir, slug, schema)
        except Exception as exc:
            msg = f"  WARN {path_template}: {exc}"
            print(msg)
            errors.append(msg)

    print(f"\nDone. Schema files in: {out_dir.resolve()}")
    if errors:
        print(f"\n{len(errors)} warning(s):")
        for e in errors:
            print(f"  {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
