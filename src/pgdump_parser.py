"""
ClearPass DB backup (tipsdb .pgdump) -> raw object model.

Produces the same dict shape as src/parser.parse() so policy_ir.build(),
the flow compiler, policy details and the API are shared by both inputs.
What the DB adds over an XML export:
- `precedence` on every service: tips_service.order_no, the real ClearPass
  evaluation order (the export is grouped by service type instead)
- every configured object, not only the ones reachable from exported services
- profile types the export can't carry (SNMP, Agent) and DUR configuration

Entry points:
  parse_pgdump(path) -> raw model          (runs pg_restore)
  raw_from_tables(tables) -> raw model     (pure; tests use committed COPY text)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .pgdump_reader import read_pgdump
from .pgdump_rules import policy_rules, service_match

Row = dict[str, Any]
Tables = dict[str, list[Row]]

# Profile attributes whose literal values are secrets. ClearPass blanks these
# in XML exports (e.g. Aruba-MPSK-Passphrase); the DB holds them in clear, so
# literal values are masked here. Template references like
# "%{Endpoint:MPSK}" are not secrets and are kept.
_SECRET_ATTRIBUTE = re.compile(r"pass(word|phrase)|psk|secret|community|(^|[-_:])key($|[-_])", re.IGNORECASE)
HIDDEN_VALUE = "(hidden)"


def _mask_secret(attr: dict[str, str]) -> dict[str, str]:
    if not _SECRET_ATTRIBUTE.search(attr.get("name", "")):
        return attr
    value = attr.get("value", "")
    if not value or value.startswith("%{"):
        return attr
    return {**attr, "value": HIDDEN_VALUE, "displayValue": HIDDEN_VALUE}


# tips_service.service_type -> canonical serviceType (as the XML parser emits)
_SERVICE_TYPES = {
    "RADIUS": "RADIUS",
    "TACACS": "TACACS",
    "APPLICATION": "APPLICATION",
    "WEBAUTH": "WEBAUTH",
}


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in ("t", "true", "1", "yes")


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return default


def _ordered_ids(rows: list[Row], key: str, id_col: str) -> dict[str, list[str]]:
    """Join-table rows -> {owner id: [member ids in order_no order]}."""
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        grouped[_s(r.get(key))].append((_int(r.get("order_no")), _s(r.get(id_col))))
    return {k: [i for _, i in sorted(v)] for k, v in grouped.items()}


def _names(ids: list[str], by_id: dict[str, str]) -> list[str]:
    return [by_id[i] for i in ids if i in by_id]


def parse_pgdump(path: str | Path) -> dict[str, Any]:
    """Read a ClearPass DB backup and return the raw object model."""
    return raw_from_tables(read_pgdump(path))


def raw_from_tables(t: Tables) -> dict[str, Any]:
    rows = lambda name: t.get(name, [])  # noqa: E731
    warnings: list[str] = []

    # --- name lookups -------------------------------------------------------
    role_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_role")}
    method_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_auth_methods")}
    source_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_auth_sources")}
    rm_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_role_mapping_policy")}
    ep_names = {_s(r["id"]): _s(r["policy_name"]) for r in rows("tips_enf_policy")}
    proxy_names = {_s(r["id"]): _s(r["proxy_name"]) for r in rows("tips_proxy_server")}
    nad_group_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_nad_group")}
    profile_tables = (
        "tips_enf_profile_radius", "tips_enf_profile_radius_coa", "tips_enf_profile_post_auth",
        "tips_enf_profile_tacacs", "tips_enf_profile_app", "tips_enf_profile_snmp",
        "tips_enf_profile_agent",
    )
    profile_names = {_s(r["id"]): _s(r["name"]) for tbl in profile_tables for r in rows(tbl)}

    vendor_names = {_s(r["vendor_id"]): _s(r["vendor_name"]) for r in rows("tips_dic_vendor_info")}
    rad_attr_names = {
        (_s(r["vendor_id"]), _s(r["attr_id"])): _s(r["attr_name"]) for r in rows("tips_dic_rad_attributes")
    }
    tacacs_service_names = {
        _s(r["id"]): _s(r.get("disp_name") or r.get("name")) for r in rows("tips_dic_tacacs_service")
    }
    internal_attrs = {
        _s(r["id"]): (_s(r.get("dic_prefix")), _s(r.get("attr_name"))) for r in rows("tips_dic_internal")
    }
    coa_template_names = {_s(r["id"]): _s(r["name"]) for r in rows("tips_radius_coa_templates")}

    def nad_groups(table: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for r in rows(table):
            name = nad_group_names.get(_s(r["nad_group_id"]))
            if name:
                out[_s(r["profile_id"])].append(name)
        return {k: sorted(v) for k, v in out.items()}

    def rad_params(table: str) -> dict[str, list[dict[str, str]]]:
        out: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
        for r in rows(table):
            vendor, attr = _s(r["vendor_id"]), _s(r["attr_id"])
            name = rad_attr_names.get((vendor, attr), f"Attribute-{attr}")
            value = _s(r.get("attr_value"))
            out[_s(r["profile_id"])].append((_int(r.get("order_no")), {
                "name": name,
                "type": f"Radius:{vendor_names.get(vendor, vendor)}",
                "value": value,
                "displayValue": _s(r.get("attr_disp_value")) or value,
            }))
        return {k: [a for _, a in sorted(v, key=lambda x: x[0])] for k, v in out.items()}

    def simple_params(table: str, attr_type: str = "") -> dict[str, list[dict[str, str]]]:
        out: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in sorted(rows(table), key=lambda r: _int(r.get("id"))):
            value = _s(r.get("attr_value"))
            out[_s(r["profile_id"])].append({
                "name": _s(r.get("attr_name")),
                "type": attr_type,
                "value": value,
                "displayValue": _s(r.get("attr_disp_value")) or value,
            })
        return out

    # --- auth methods / sources / roles -----------------------------------
    inner = _ordered_ids(rows("tips_auth_method_inner"), "method_id", "inner_method_id")
    auth_methods = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "methodType": _s(r.get("method_type")),
            "params": {},  # tips_auth_method_details is not read
            "innerMethods": _names(inner.get(_s(r["id"]), []), method_names),
        }
        for r in rows("tips_auth_methods")
    ]
    auth_sources = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "type": _s(r.get("source_type")),
            "isAuthorizationSource": "true" if _bool(r.get("is_autz_source")) else "false",
            "params": {},       # connection details (tips_auth_source_details) are never read
            "filters": [],
            "authorizationSources": [],
        }
        for r in rows("tips_auth_sources")
    ]
    roles = [{"name": _s(r["name"]), "description": _s(r.get("description"))} for r in rows("tips_role")]

    # --- policies ------------------------------------------------------------
    role_mappings = []
    for r in rows("tips_role_mapping_policy"):
        algo, rules = policy_rules(
            r.get("policy_xml"), warnings, f"Role Mapping Policy '{_s(r['name'])}'",
            {"Tips:Role": role_names},
        )
        role_mappings.append({
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "ruleCombineAlgo": algo,
            "defaultRole": role_names.get(_s(r.get("dft_role_id")), ""),
            "rules": rules,
        })

    enforcement_policies = []
    for r in rows("tips_enf_policy"):
        algo, rules = policy_rules(
            r.get("policy_xml"), warnings, f"Enforcement Policy '{_s(r['policy_name'])}'",
            {"Tips:Enforcement-Profile": profile_names},
        )
        enforcement_policies.append({
            "name": _s(r["policy_name"]),
            "description": _s(r.get("description")),
            "policyType": _s(r.get("policy_type")),
            "defaultProfile": profile_names.get(_s(r.get("dft_profile_id")), ""),
            "ruleCombineAlgo": algo,
            "rules": rules,
        })

    # --- enforcement profiles ------------------------------------------------
    radius_params = rad_params("tips_enf_profile_radius_params")
    coa_params = rad_params("tips_enf_profile_radius_coa_params")
    dur_product = {_s(r["profile_id"]): _s(r.get("type")) for r in rows("role_config")}
    dur_attrs: dict[str, list[dict[str, str]]] = {}
    for r in rows("dur_role_config"):
        plugin = _s(r.get("plugin_type"))
        try:
            settings = json.loads(_s(r.get("attributes")) or "{}")
        except json.JSONDecodeError:
            warnings.append(f"Downloadable-role settings for profile id {_s(r['profile_id'])} could not be read")
            settings = {}
        attr_type = f"DUR:{plugin}".rstrip(":")
        dur_attrs[_s(r["profile_id"])] = [
            {"name": str(k), "type": attr_type, "value": _s(v), "displayValue": _s(v)}
            for k, v in settings.items()
            if not isinstance(v, (dict, list))
        ]

    radius_nad = nad_groups("tips_enf_profile_radius_nad_group")
    radius_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": _s(r.get("profile_type")),            # Accept | Reject | Drop
            "attributes": radius_params.get(_s(r["id"]), []) + dur_attrs.get(_s(r["id"]), []),
            "product": dur_product.get(_s(r["id"]), ""),
            "nadGroups": radius_nad.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_radius")
    ]

    coa_nad = nad_groups("tips_enf_profile_radius_coa_nad_group")
    coa_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": _s(r.get("profile_type")),            # CoA | Disconnect
            "template": coa_template_names.get(_s(r.get("template_id")), ""),
            "attributes": coa_params.get(_s(r["id"]), []),
            "nadGroups": coa_nad.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_radius_coa")
    ]

    post_auth_attrs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in sorted(rows("tips_enf_profile_post_auth_params"), key=lambda r: _int(r.get("id"))):
        prefix, dict_name = internal_attrs.get(_s(r.get("attr_id")), ("", ""))
        value = _s(r.get("attr_value"))
        post_auth_attrs[_s(r["profile_id"])].append({
            "name": _s(r.get("attr_name")) or dict_name,
            "type": prefix,
            "value": value,
            "displayValue": _s(r.get("attr_disp_value")) or value,
        })
    post_auth_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "postAuthType": _s(r.get("type")),
            "attributes": post_auth_attrs.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_post_auth")
    ]

    tacacs_attrs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows("tips_enf_profile_tacacs_params"):
        value = _s(r.get("attr_value"))
        tacacs_attrs[_s(r["profile_id"])].append({
            "name": _s(r.get("attr_name")),
            "type": tacacs_service_names.get(_s(r.get("service_id")), _s(r.get("service_id"))),
            "value": value,
            "displayValue": _s(r.get("attr_disp_value")) or value,
        })
    tacacs_services: dict[str, list[str]] = defaultdict(list)
    for r in rows("tips_enf_profile_tacacs_allowed_service"):
        sid = _s(r.get("tacacs_service_id"))
        tacacs_services[_s(r["profile_id"])].append(tacacs_service_names.get(sid, sid))
    tacacs_nad = nad_groups("tips_enf_profile_tacacs_nad_group")
    tacacs_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": "",
            "autzStatus": _s(r.get("autz_status")),
            "maxPrivLevel": _s(r.get("max_priv_level")),
            "attributes": tacacs_attrs.get(_s(r["id"]), []),
            "tacacsServices": tacacs_services.get(_s(r["id"]), []),
            "nadGroups": tacacs_nad.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_tacacs")
    ]

    app_params = simple_params("tips_enf_profile_app_params")
    generic_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": _s(r.get("profile_type")),            # Accept | Reject
            "type": _s(r.get("app_type")),                  # Application | HTTP | CLI
            "attributes": app_params.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_app")
    ]

    snmp_params: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows("tips_enf_profile_snmp_params"):
        value = _s(r.get("attr_value"))
        snmp_params[_s(r["profile_id"])].append(
            {"name": _s(r.get("attr_name")), "type": "SNMP", "value": value, "displayValue": value}
        )
    snmp_nad = nad_groups("tips_enf_profile_snmp_nad_group")
    agent_params = simple_params("tips_enf_profile_agent_params", "Agent")
    other_profiles = [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": "",
            "profileType": "snmp",
            "attributes": snmp_params.get(_s(r["id"]), []),
            "nadGroups": snmp_nad.get(_s(r["id"]), []),
            "extras": [],
        }
        for r in rows("tips_enf_profile_snmp")
    ] + [
        {
            "name": _s(r["name"]),
            "description": _s(r.get("description")),
            "action": "",
            "profileType": "agent",
            "attributes": agent_params.get(_s(r["id"]), []),
            "nadGroups": [],
            "extras": [],
        }
        for r in rows("tips_enf_profile_agent")
    ]

    for plist in (radius_profiles, coa_profiles, post_auth_profiles, tacacs_profiles,
                  generic_profiles, other_profiles):
        for prof in plist:
            prof["attributes"] = [_mask_secret(a) for a in prof["attributes"]]

    # --- services -------------------------------------------------------------
    svc_methods = _ordered_ids(rows("tips_service_auth_methods"), "service_id", "method_id")
    svc_sources = _ordered_ids(rows("tips_service_auth_source"), "service_id", "source_id")
    svc_autz = _ordered_ids(rows("tips_service_autz_source"), "service_id", "source_id")
    svc_rm = _ordered_ids(rows("tips_service_role_mapping"), "service_id", "role_mapping_id")
    svc_ep = _ordered_ids(rows("tips_service_policy"), "service_id", "policy_id")
    svc_proxies = _ordered_ids(rows("tips_service_proxies"), "service_id", "proxy_server_id")
    svc_acct: dict[str, list[str]] = defaultdict(list)
    for r in rows("tips_service_acct_proxy_servers"):
        svc_acct[_s(r["service_id"])].append(_s(r["proxy_server_id"]))
    svc_coa: dict[str, list[Row]] = defaultdict(list)
    for r in rows("tips_service_coa"):
        svc_coa[_s(r["service_id"])].append(r)

    services = []
    for r in sorted(rows("tips_service"), key=lambda r: (_int(r.get("order_no")), _s(r.get("name")))):
        sid = _s(r["id"])
        name = _s(r["name"])
        template = _s(r.get("service_template"))
        is_proxy = template == "RADIUS_PROXY"
        stype = "RADIUS_PROXY" if is_proxy else _SERVICE_TYPES.get(_s(r.get("service_type")).upper(),
                                                                   _s(r.get("service_type")).upper())
        coa_rows = svc_coa.get(sid, [])
        entry: dict[str, Any] = {
            "name": name,
            "description": _s(r.get("description")),
            "enabled": "true" if _bool(r.get("enabled")) else "false",
            "serviceType": stype,
            "serviceTemplate": template,
            "matchExpression": service_match(r.get("rule_xml"), warnings, f"Service '{name}' match rule"),
            "authMethods": [] if is_proxy else _names(svc_methods.get(sid, []), method_names),
            "authSources": [] if is_proxy else _names(svc_sources.get(sid, []), source_names),
            "autzSources": [] if is_proxy else _names(svc_autz.get(sid, []), source_names),
            "roleMappings": [] if is_proxy else _names(svc_rm.get(sid, []), rm_names),
            "enfPolicies": _names(svc_ep.get(sid, []), ep_names),
            "exportOrder": None,
            "precedence": _int(r["order_no"]) if r.get("order_no") is not None else None,
            "monitorMode": _bool(r.get("monitor_mode")),
            "useCachedResults": _bool(r.get("use_cached_results")),
            "stripUsername": _bool(r.get("strip_username")),
            "profilerEnabled": _bool(r.get("profiler_enabled")),
            "postureEnabled": _bool(r.get("posture_enabled")),
            "auditEnabled": _bool(r.get("audit_enabled")),
            "acctProxyTargets": _names(svc_acct.get(sid, []), proxy_names),
            "proxyForwardType": _s(r.get("proxy_load_balance_type")) if is_proxy else "",
            "proxyAccountRequests": _bool(r.get("proxy_acct_requests")) if is_proxy else False,
            "profilerCoaProfile": profile_names.get(_s(coa_rows[0].get("coa_profile_id")), "") if coa_rows else "",
            "profilerCategories": [_s(c.get("device_category")) for c in coa_rows if c.get("device_category")],
            "stripRules": [s.strip() for s in _s(r.get("strip_rules_csv")).split(",") if s.strip()],
            "extras": [],
        }
        if is_proxy:
            entry["proxyNames"] = _names(svc_proxies.get(sid, []), proxy_names)
        services.append(entry)

    return {
        "format": "pgdump",
        "services": services,
        "authMethods": auth_methods,
        "authSources": auth_sources,
        "roles": roles,
        "roleMappings": role_mappings,
        "enforcementPolicies": enforcement_policies,
        "radiusEnfProfiles": radius_profiles,
        "postAuthEnfProfiles": post_auth_profiles,
        "tacacsEnfProfiles": tacacs_profiles,
        "radiusCoaEnfProfiles": coa_profiles,
        "genericEnfProfiles": generic_profiles,
        "otherEnfProfiles": other_profiles,
        "warnings": warnings,
    }
