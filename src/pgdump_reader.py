"""
ClearPass DB backup reader (tipsdb .pgdump, PostgreSQL custom format).

Reads policy tables out of a ClearPass configuration backup WITHOUT a
PostgreSQL server: `pg_restore --data-only -t <table> -f -` turns the archive
into COPY text, which `parse_copy_text` decodes into rows.

Security model
--------------
A tipsdb backup contains secret-bearing tables (admin/local users, NAD shared
secrets, certificates and keys, OAuth clients, external accounts). This module
only ever asks pg_restore for the tables in ALLOWED_COLUMNS, and drops every
column not listed there while parsing. Secret columns that live inside an
allowed table (e.g. tips_proxy_server.shared_secret) are simply not listed.
pg_restore's output is held in memory, never written to disk or logged.

Entry points:
  read_pgdump(path) -> dict[table, list[row dict]]
  parse_copy_text(text) -> dict[table, list[row dict]]   (pure; used by tests)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

PGDUMP_MAGIC = b"PGDMP"

# table -> columns kept. Anything not listed is never requested (tables) or
# is discarded on parse (columns). Keep this the single source of truth.
ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    # --- services and their joins ---
    "tips_service": (
        "id", "name", "description", "rule_xml", "order_no", "enabled", "monitor_mode",
        "service_type", "service_template", "posture_enabled", "audit_enabled",
        "profiler_enabled", "has_proxy", "has_acct_proxy", "proxy_load_balance_type",
        "proxy_acct_requests", "strip_username", "strip_rules_csv", "use_cached_results",
    ),
    "tips_service_auth_methods": ("service_id", "order_no", "method_id"),
    "tips_service_auth_source": ("service_id", "order_no", "source_id"),
    "tips_service_autz_source": ("service_id", "order_no", "source_id"),
    "tips_service_role_mapping": ("service_id", "order_no", "role_mapping_id"),
    "tips_service_policy": ("service_id", "order_no", "policy_id"),
    "tips_service_proxies": ("service_id", "order_no", "proxy_server_id"),
    "tips_service_acct_proxy_servers": ("service_id", "proxy_server_id"),
    "tips_service_coa": ("service_id", "device_category", "coa_profile_id"),
    "tips_proxy_server": ("id", "proxy_name"),  # NOT shared_secret / host details
    # --- policies, roles, authentication ---
    "tips_role": ("id", "name", "description"),
    "tips_role_mapping_policy": ("id", "name", "description", "policy_xml", "dft_role_id"),
    "tips_enf_policy": ("id", "policy_name", "description", "policy_xml", "dft_profile_id", "policy_type"),
    "tips_auth_methods": ("id", "name", "description", "method_type"),
    "tips_auth_method_inner": ("method_id", "inner_method_id", "order_no"),
    # NOT tips_auth_source_details (bind credentials) — names/types only.
    "tips_auth_sources": ("id", "name", "description", "source_type", "is_autz_source"),
    "tips_nad_group": ("id", "name"),  # NOT members (device IPs)
    # --- enforcement profiles ---
    "tips_enf_profile_radius": ("id", "name", "profile_type", "template", "description"),
    "tips_enf_profile_radius_params": (
        "profile_id", "vendor_id", "attr_id", "attr_value", "attr_disp_value", "order_no",
    ),
    "tips_enf_profile_radius_nad_group": ("profile_id", "nad_group_id"),
    "tips_enf_profile_radius_coa": ("id", "name", "template", "template_id", "description", "profile_type"),
    "tips_radius_coa_templates": ("id", "name"),
    "tips_enf_profile_radius_coa_params": (
        "profile_id", "vendor_id", "attr_id", "attr_value", "attr_disp_value", "order_no",
    ),
    "tips_enf_profile_radius_coa_nad_group": ("profile_id", "nad_group_id"),
    "tips_enf_profile_post_auth": ("id", "name", "description", "template", "type"),
    "tips_enf_profile_post_auth_params": ("id", "profile_id", "attr_id", "attr_name", "attr_value", "attr_disp_value"),
    "tips_enf_profile_tacacs": (
        "id", "name", "template", "description", "max_priv_level", "service_type",
        "autz_status", "permit_unmatched_cmd",
    ),
    "tips_enf_profile_tacacs_params": ("profile_id", "service_id", "attr_name", "attr_value", "attr_disp_value"),
    "tips_enf_profile_tacacs_allowed_service": ("profile_id", "tacacs_service_id"),
    "tips_enf_profile_tacacs_nad_group": ("profile_id", "nad_group_id"),
    "tips_enf_profile_app": ("id", "name", "template", "description", "app_type", "profile_type"),
    "tips_enf_profile_app_params": ("id", "profile_id", "attr_name", "attr_value", "attr_disp_value"),
    "tips_enf_profile_app_nad_group": ("profile_id", "nad_group_id"),
    "tips_enf_profile_snmp": ("id", "name", "template", "description"),
    "tips_enf_profile_snmp_params": ("profile_id", "attr_name", "attr_value"),
    "tips_enf_profile_snmp_nad_group": ("profile_id", "nad_group_id"),
    "tips_enf_profile_agent": ("id", "name", "template", "description", "type"),
    "tips_enf_profile_agent_params": ("id", "profile_id", "attr_name", "attr_value", "attr_disp_value"),
    # Aruba Downloadable User Role (DUR) configuration
    "role_config": ("profile_id", "type", "version"),
    "dur_role_config": ("profile_id", "plugin_type", "attributes"),
    # --- dictionaries (id -> display names) ---
    "tips_dic_rad_attributes": ("vendor_id", "attr_name", "attr_id", "attr_type"),
    "tips_dic_vendor_info": ("vendor_name", "vendor_id"),
    "tips_dic_tacacs_service": ("id", "name", "disp_name"),
    "tips_dic_internal": ("id", "dic_prefix", "attr_name"),
}

# Tables that must never be read, even if someone adds them above by mistake.
# Guarded by tests/test_pgdump.py.
FORBIDDEN_TABLE_PATTERNS: tuple[str, ...] = (
    r"local_user", r"admin_user", r"auth_source_details", r"nad_client", r"nad_.*_config",
    r"oauth", r"cert", r"csr", r"key", r"secret", r"password", r"credential", r"external_account",
    r"endpoint",  # endpoint data is deferred until offline endpoint matching is designed
)

PG_RESTORE_TIMEOUT_S = 120
_FALLBACK_PG_RESTORE = ("/opt/homebrew/opt/libpq/bin/pg_restore", "/usr/local/opt/libpq/bin/pg_restore")


class PgDumpError(Exception):
    """The file is not a readable ClearPass DB backup."""


class PgRestoreNotFound(PgDumpError):
    """pg_restore is not installed (install the PostgreSQL client tools)."""


def is_pgdump(data: bytes) -> bool:
    """True for a PostgreSQL custom-format archive (pg_dump -Fc)."""
    return data[:5] == PGDUMP_MAGIC


def find_pg_restore() -> str:
    """Locate pg_restore: $PG_RESTORE, then PATH, then Homebrew libpq."""
    env = os.environ.get("PG_RESTORE")
    if env:
        if Path(env).is_file():
            return env
        raise PgRestoreNotFound(f"PG_RESTORE points to a missing file: {env}")
    found = shutil.which("pg_restore")
    if found:
        return found
    for candidate in _FALLBACK_PG_RESTORE:
        if Path(candidate).is_file():
            return candidate
    raise PgRestoreNotFound(
        "pg_restore not found. Install the PostgreSQL client tools "
        "(e.g. apt install postgresql-client, brew install libpq) or set PG_RESTORE."
    )


def read_pgdump(path: str | Path, *, pg_restore: str | None = None) -> dict[str, list[dict[str, str | None]]]:
    """Extract the allow-listed tables of a tipsdb backup as rows."""
    exe = pg_restore or find_pg_restore()
    argv = [exe, "--data-only", "--file=-"]
    for table in sorted(ALLOWED_COLUMNS):
        argv.append(f"--table={table}")
    argv.append(str(path))
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=PG_RESTORE_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PgDumpError(f"pg_restore timed out after {PG_RESTORE_TIMEOUT_S}s") from exc
    if proc.returncode != 0:
        # pg_restore's stderr describes archive problems; it never contains row data.
        detail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise PgDumpError("pg_restore could not read the file: " + (detail[0] if detail else "unknown error"))
    return parse_copy_text(proc.stdout.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# COPY text format
# ---------------------------------------------------------------------------
# https://www.postgresql.org/docs/current/sql-copy.html  (Text Format)
_COPY_HEADER = re.compile(r"^COPY (?:\"?[\w]+\"?\.)?\"?(\w+)\"? \((.*)\) FROM stdin;$")
_SIMPLE_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
_ESCAPE = re.compile(r"\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)")


def _unescape_field(field: str) -> str | None:
    if field == r"\N":
        return None
    if "\\" not in field:
        return field

    def sub(m: re.Match) -> str:
        tok = m.group(1)
        if tok in _SIMPLE_ESCAPES:
            return _SIMPLE_ESCAPES[tok]
        if tok[0] == "x" and len(tok) > 1:
            return chr(int(tok[1:], 16))
        if tok.isdigit() and all(c in "01234567" for c in tok):
            return chr(int(tok, 8))
        return tok  # backslash followed by any other char stands for that char

    return _ESCAPE.sub(sub, field)


def parse_copy_text(
    text: str, allowed: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, list[dict[str, str | None]]]:
    """Decode pg_restore COPY text into {table: [row, ...]}.

    Only tables in `allowed` (default ALLOWED_COLUMNS) are kept, and each row
    keeps only that table's allowed columns. Values are str, or None for NULL.
    """
    allowed = ALLOWED_COLUMNS if allowed is None else allowed
    tables: dict[str, list[dict[str, str | None]]] = {}
    current: str | None = None
    columns: list[str] = []
    keep: list[int] = []
    for line in text.split("\n"):
        if current is None:
            m = _COPY_HEADER.match(line)
            if m and m.group(1) in allowed:
                current = m.group(1)
                columns = [c.strip().strip('"') for c in m.group(2).split(",")]
                wanted = set(allowed[current])
                keep = [i for i, c in enumerate(columns) if c in wanted]
                tables.setdefault(current, [])
            elif m:
                current = ""  # a table we don't want: skip its rows
            continue
        if line == "\\.":
            current = None
            continue
        if current == "":
            continue
        fields = line.split("\t")
        tables[current].append({columns[i]: _unescape_field(fields[i]) for i in keep if i < len(fields)})
    return tables


_REVERSE_ESCAPES = {"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r", "\b": "\\b", "\f": "\\f", "\v": "\\v"}


def _escape_field(value: str | None) -> str:
    if value is None:
        return r"\N"
    return "".join(_REVERSE_ESCAPES.get(ch, ch) for ch in value)


def format_copy_text(tables: dict[str, list[dict[str, str | None]]]) -> str:
    """Inverse of parse_copy_text, for writing test fixtures.

    Tables are written in sorted order with columns in ALLOWED_COLUMNS order,
    so the output is deterministic and diff-friendly.
    """
    out: list[str] = []
    for table in sorted(tables):
        cols = [c for c in ALLOWED_COLUMNS.get(table, ()) if any(c in r for r in tables[table])]
        out.append(f"COPY public.{table} ({', '.join(cols)}) FROM stdin;")
        for row in tables[table]:
            out.append("\t".join(_escape_field(row.get(c)) for c in cols))
        out.append("\\.")
        out.append("")
    return "\n".join(out)
