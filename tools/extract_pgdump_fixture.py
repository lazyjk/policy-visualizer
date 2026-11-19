#!/usr/bin/env python3
"""
Build a committable test fixture from a ClearPass DB backup (.pgdump).

The backup itself must never be committed (it holds secret-bearing tables).
This tool writes only what the app reads, as PostgreSQL COPY text:

1. pg_restore of the allow-listed tables/columns (src/pgdump_reader.py)
2. literal secret attribute values masked (same rule the app applies)
3. dictionaries trimmed to the rows the profiles reference
4. identifying lab values replaced via tools/sanitize_fixture.py's map
5. a leftover check (mapped values, non-documentation IPv4s) — aborts on failure

Usage:
    python tools/extract_pgdump_fixture.py reference-files/lab-kitchen-sink-tipsdb.pgdump \\
        tests/fixtures/pgdump/LabKitchenSink.copy.txt [--map reference-files/sanitize_map.json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sanitize_fixture  # noqa: E402  (same directory)
from src.pgdump_parser import HIDDEN_VALUE, _SECRET_ATTRIBUTE  # noqa: E402
from src.pgdump_reader import format_copy_text, read_pgdump  # noqa: E402

_RAD_PARAM_TABLES = ("tips_enf_profile_radius_params", "tips_enf_profile_radius_coa_params")
_NAMED_PARAM_TABLES = (
    "tips_enf_profile_post_auth_params", "tips_enf_profile_tacacs_params",
    "tips_enf_profile_app_params", "tips_enf_profile_snmp_params", "tips_enf_profile_agent_params",
)


def _mask(row: dict, name: str) -> None:
    value = row.get("attr_value") or ""
    if _SECRET_ATTRIBUTE.search(name or "") and value and not value.startswith("%{"):
        row["attr_value"] = HIDDEN_VALUE
        if "attr_disp_value" in row:
            row["attr_disp_value"] = HIDDEN_VALUE


def extract(tables: dict, pairs: list[tuple[str, str]]) -> dict:
    rad_dic = {(r["vendor_id"], r["attr_id"]): r for r in tables.get("tips_dic_rad_attributes", [])}

    # 2. mask secrets
    for t in _RAD_PARAM_TABLES:
        for r in tables.get(t, []):
            _mask(r, (rad_dic.get((r["vendor_id"], r["attr_id"])) or {}).get("attr_name", ""))
    for t in _NAMED_PARAM_TABLES:
        for r in tables.get(t, []):
            _mask(r, r.get("attr_name") or "")

    # 3. trim dictionaries to referenced rows
    used_rad = {(r["vendor_id"], r["attr_id"]) for t in _RAD_PARAM_TABLES for r in tables.get(t, [])}
    tables["tips_dic_rad_attributes"] = [
        r for r in tables.get("tips_dic_rad_attributes", []) if (r["vendor_id"], r["attr_id"]) in used_rad
    ]
    used_vendors = {v for v, _ in used_rad}
    tables["tips_dic_vendor_info"] = [
        r for r in tables.get("tips_dic_vendor_info", []) if r["vendor_id"] in used_vendors
    ]
    used_internal = {r["attr_id"] for r in tables.get("tips_enf_profile_post_auth_params", [])}
    tables["tips_dic_internal"] = [r for r in tables.get("tips_dic_internal", []) if r["id"] in used_internal]
    used_tacacs = {r["service_id"] for r in tables.get("tips_enf_profile_tacacs_params", [])} | {
        r["tacacs_service_id"] for r in tables.get("tips_enf_profile_tacacs_allowed_service", [])
    }
    tables["tips_dic_tacacs_service"] = [
        r for r in tables.get("tips_dic_tacacs_service", []) if r["id"] in used_tacacs
    ]

    # 4. sanitize every string value
    return {
        t: [{k: (sanitize_fixture.sanitize(v, pairs) if isinstance(v, str) else v) for k, v in r.items()} for r in rows]
        for t, rows in tables.items()
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--map", type=Path, default=sanitize_fixture.DEFAULT_MAP)
    args = ap.parse_args(argv)

    pairs = sanitize_fixture.load_map(args.map)
    text = format_copy_text(extract(read_pgdump(args.dump), pairs))

    problems = sanitize_fixture.leftovers(text, pairs)
    if problems:
        for p in problems:
            print(f"refusing to write {args.output}: {p}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.output} ({len(text.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
