"""
Phase 1: XML Parsing Layer

Parses a ClearPass TipsContents XML export into a raw object model
(plain dicts/lists close to the XML structure). Rule order is preserved.
"""
from __future__ import annotations

import defusedxml.ElementTree as ET
from pathlib import Path
from typing import Any

NS = "http://www.avendasys.com/tipsapiDefs/1.0"


def _tag(local: str) -> str:
    return f"{{{NS}}}{local}"


def _nvpairs(element: ET.Element) -> dict[str, str]:
    return {
        nvp.get("name", ""): nvp.get("value", "")
        for nvp in element.findall(_tag("NVPair"))
    }


def _rule_expressions(rule_expr_el: ET.Element | None) -> dict[str, Any] | None:
    if rule_expr_el is None:
        return None
    attrs = []
    for ra in rule_expr_el.findall(f".//{_tag('RuleAttribute')}"):
        attrs.append({
            "name": ra.get("name", ""),
            "type": ra.get("type", ""),
            "operator": ra.get("operator", ""),
            "value": ra.get("value", ""),
            "displayValue": ra.get("displayValue", ""),
        })
    return {
        "operator": rule_expr_el.get("operator", ""),
        "displayOperator": rule_expr_el.get("displayOperator", ""),
        "attributes": attrs,
    }


def _parse_rule(rule_el: ET.Element, index: int) -> dict[str, Any]:
    condition_el = rule_el.find(_tag("Condition"))
    expr_el = condition_el.find(_tag("Expression")) if condition_el is not None else None

    results = []
    result_list_el = rule_el.find(_tag("ResultList"))
    if result_list_el is not None:
        for rr in result_list_el.findall(_tag("RuleResult")):
            results.append({
                "name": rr.get("name", ""),
                "type": rr.get("type", ""),
                "value": rr.get("value", ""),
                "displayValue": rr.get("displayValue", ""),
            })

    return {
        "index": index,
        "expression": _rule_expressions(expr_el),
        "results": results,
    }


def _string_list(parent: ET.Element, container_tag: str) -> list[str]:
    container = parent.find(_tag(container_tag))
    if container is None:
        return []
    return [s.text or "" for s in container.findall(_tag("string"))]


# Service element name -> canonical serviceType. Iteration order defines the
# grouping order of model["services"] (unchanged from earlier releases).
_SERVICE_ELEMENTS: list[tuple[str, str]] = [
    ("RadiusEnforcementService", "RADIUS"),
    ("TacacsEnforcementService", "TACACS"),
    ("RadiusProxyService", "RADIUS_PROXY"),
    ("AvendaWebAuthService", "WEBAUTH"),
    ("AvendaAppAuthService", "APPLICATION"),
]

# XML service attribute -> raw-model key. Missing attributes default to False
# (TACACS/App/WebAuth services only carry a subset of these).
_SERVICE_FLAG_ATTRS: dict[str, str] = {
    "monitor": "monitorMode",
    "useCachedResults": "useCachedResults",
    "stripUsername": "stripUsername",
    "profilerEnabled": "profilerEnabled",
    "postureEnabled": "postureEnabled",
    "auditEnabled": "auditEnabled",
}


# ---------------------------------------------------------------------------
# Catch-all for settings this parser does not interpret
# ---------------------------------------------------------------------------
# Anything on a service or profile that is not listed here is captured as an
# "extra" (path → value) so it is never silently dropped: users with features
# we have no fixtures for still see the raw settings in the inspector.

_MAX_EXTRAS = 200

# Attributes read explicitly, or deliberately ignored as noise.
_KNOWN_SERVICE_ATTRS = {"name", "description", "enabled", "acctProxyTargets", "stripRulesCsv", *_SERVICE_FLAG_ATTRS}
_KNOWN_SERVICE_CHILDREN = {
    "RuleExpression", "ServiceTemplate", "AuthMethodNameList", "AuthSourceNameList",
    "AutzSourceNameList", "RoleMappingNameList", "EnfPolicyNameList", "ProxyNameList",
}

# element tag -> (known attributes, known child elements)
_KNOWN_PROFILE_PARTS: dict[str, tuple[set[str], set[str]]] = {
    "RadiusEnfProfile": (
        {"name", "description", "action", "product", "productVersion"},
        {"AttributeList", "DURRoleConfig", "NadGroupNameList"},
    ),
    "PostAuthEnfProfile": ({"name", "description", "postAuthType"}, {"AttributeList"}),
    "TacacsEnfProfile": (
        {"name", "description", "action", "autzStatus", "maxPrivLevel"},
        {"AttributeList", "NadGroupNameList"},
    ),
    "RadiusCoAEnfProfile": (
        {"name", "description", "action", "template"},
        {"AttributeList", "NadGroupNameList"},
    ),
    "GenericEnfProfile": ({"name", "description", "action", "type"}, {"ProfileParams"}),
}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _element_label(el: ET.Element) -> str:
    name = el.get("name")
    return f"{_local(el.tag)}[{name}]" if name else _local(el.tag)


def _flatten(el: ET.Element, path: str, out: list[dict[str, str]]) -> None:
    """Depth-first: every attribute (except `name`, used in the path) and any
    text becomes one {path, value} entry."""
    for key, value in el.attrib.items():
        if key == "name" or len(out) > _MAX_EXTRAS:
            continue
        out.append({"path": f"{path}/@{key}", "value": value})
    text = (el.text or "").strip()
    if text and len(out) <= _MAX_EXTRAS:
        out.append({"path": path, "value": text})
    for child in el:
        _flatten(child, f"{path}/{_element_label(child)}", out)


def _extras(el: ET.Element, known_attrs: set[str], known_children: set[str]) -> list[dict[str, str]]:
    """Settings on `el` the parser does not interpret, as flat {path, value} rows.

    Element-level attributes that are empty or "false" are skipped (a disabled
    unknown option is noise); nested content is reported in full.
    """
    out: list[dict[str, str]] = []
    for key, value in el.attrib.items():
        if key in known_attrs or value.strip().lower() in ("", "false"):
            continue
        out.append({"path": f"@{key}", "value": value})
    for child in el:
        tag = _local(child.tag)
        if tag == "DURRoleConfig" and tag in known_children:
            # DUR <Attribute>s are interpreted; anything else nested inside
            # (ACLs, policies on other DUR plugins) is not.
            for sub in child:
                if _local(sub.tag) != "Attribute":
                    _flatten(sub, f"{tag}/{_element_label(sub)}", out)
            continue
        if tag in known_children:
            continue
        _flatten(child, _element_label(child), out)
    if len(out) > _MAX_EXTRAS:
        out = out[:_MAX_EXTRAS]
        out.append({"path": "…", "value": f"truncated after {_MAX_EXTRAS} entries"})
    return out


def _profile_extras(el: ET.Element) -> list[dict[str, str]]:
    known_attrs, known_children = _KNOWN_PROFILE_PARTS.get(_local(el.tag), (set(), set()))
    return _extras(el, known_attrs, known_children)


def _bool_attr(el: ET.Element, attr: str, default: bool = False) -> bool:
    raw = el.get(attr)
    if raw is None:
        return default
    return raw.strip().lower() == "true"


def _service_flags(svc: ET.Element) -> dict[str, bool]:
    return {key: _bool_attr(svc, attr) for attr, key in _SERVICE_FLAG_ATTRS.items()}


def _attribute_list(el: ET.Element) -> list[dict[str, str]]:
    """Profile attributes from the element's *direct* <AttributeList> child.

    Deliberately not a descendant search: <RadiusCOATemplates> carry their own
    <Attribute> elements that must not leak into profile attributes.
    """
    container = el.find(_tag("AttributeList"))
    if container is None:
        return []
    return [
        {
            "name": a.get("name", ""),
            "type": a.get("type", ""),
            "value": a.get("value", ""),
            "displayValue": a.get("displayValue", ""),
        }
        for a in container.findall(_tag("Attribute"))
    ]


def _dur_attributes(el: ET.Element) -> list[dict[str, str]]:
    """Aruba Downloadable User Role settings from a profile's <DURRoleConfig>.

    Returned in the same shape as _attribute_list() with type
    "DUR:<pluginType>" so they flow through the same IR/UI path. All
    descendant <Attribute name value> elements are read, so plugin variants
    that nest settings deeper are still captured.
    """
    dur = el.find(_tag("DURRoleConfig"))
    if dur is None:
        return []
    attr_type = f"DUR:{dur.get('pluginType', '')}".rstrip(":")
    return [
        {
            "name": a.get("name", ""),
            "type": attr_type,
            "value": a.get("value", ""),
            "displayValue": a.get("displayValue", a.get("value", "")),
        }
        for a in dur.iter(_tag("Attribute"))
    ]


def _parse_service(svc: ET.Element, service_type: str, export_order: int | None) -> dict[str, Any]:
    expr_el = svc.find(f".//{_tag('RuleExpression')}")
    is_proxy = service_type == "RADIUS_PROXY"
    entry: dict[str, Any] = {
        "name": svc.get("name", ""),
        "description": svc.get("description", ""),
        "enabled": svc.get("enabled", "true"),
        "serviceType": service_type,
        "serviceTemplate": (svc.findtext(_tag("ServiceTemplate")) or "").strip(),
        "matchExpression": _rule_expressions(expr_el),
        "authMethods": [] if is_proxy else _string_list(svc, "AuthMethodNameList"),
        "authSources": [] if is_proxy else _string_list(svc, "AuthSourceNameList"),
        "autzSources": [] if is_proxy else _string_list(svc, "AutzSourceNameList"),
        "roleMappings": [] if is_proxy else _string_list(svc, "RoleMappingNameList"),
        "enfPolicies": _string_list(svc, "EnfPolicyNameList"),
        "exportOrder": export_order,
        **_service_flags(svc),
        # Strip-username rules, e.g. "user:@, \\:user" -> ["user:@", "\\:user"]
        "stripRules": [r.strip() for r in svc.get("stripRulesCsv", "").split(",") if r.strip()],
        "extras": _extras(svc, _KNOWN_SERVICE_ATTRS, _KNOWN_SERVICE_CHILDREN),
    }
    if is_proxy:
        entry["proxyNames"] = _string_list(svc, "ProxyNameList")
    return entry


def parse(xml_path: str | Path) -> dict[str, Any]:
    """Parse a ClearPass XML export and return the raw object model."""
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    model: dict[str, Any] = {
        "services": [],
        "authMethods": [],
        "authSources": [],
        "roles": [],
        "roleMappings": [],
        "enforcementPolicies": [],
        "radiusEnfProfiles": [],
        "postAuthEnfProfiles": [],
        "tacacsEnfProfiles": [],
        "radiusCoaEnfProfiles": [],
        "genericEnfProfiles": [],
        "otherEnfProfiles": [],
    }

    # --- Services (all five element types) ---
    # Document order across *all* service elements (used for export_order).
    service_tags = {_tag(t) for t, _ in _SERVICE_ELEMENTS}
    doc_order = {id(el): i for i, el in enumerate(e for e in root.iter() if e.tag in service_tags)}
    for element_name, service_type in _SERVICE_ELEMENTS:
        for svc in root.findall(f".//{_tag(element_name)}"):
            model["services"].append(_parse_service(svc, service_type, doc_order.get(id(svc))))

    # --- Auth Methods ---
    for am in root.findall(f".//{_tag('AuthMethod')}"):
        inner = [s.text or "" for s in am.findall(f".//{_tag('string')}")] if am.find(_tag("InnerMethodNames")) is not None else []
        model["authMethods"].append({
            "name": am.get("name", ""),
            "description": am.get("description", ""),
            "methodType": am.get("methodType", ""),
            "params": _nvpairs(am),
            "innerMethods": inner,
        })

    # --- Auth Sources ---
    for src in root.findall(f".//{_tag('AuthSource')}"):
        filters = []
        for f in src.findall(f".//{_tag('Filter')}"):
            filter_attrs = []
            for a in f.findall(_tag("Attributes") + f"/{_tag('Attribute')}"):
                filter_attrs.append({
                    "aliasName": a.get("aliasName", ""),
                    "attrName": a.get("attrName", ""),
                    "attrDataType": a.get("attrDataType", ""),
                })
            filters.append({
                "filterName": f.get("filterName", ""),
                "filterQuery": f.get("filterQuery", ""),
                "attributes": filter_attrs,
            })
        auth_sources = [az.text or "" for az in src.findall(f".//{_tag('AuthorizationSource')}")]
        model["authSources"].append({
            "name": src.get("name", ""),
            "description": src.get("description", ""),
            "type": src.get("type", ""),
            "isAuthorizationSource": src.get("isAuthorizationSource", "false"),
            "params": _nvpairs(src),
            "filters": filters,
            "authorizationSources": auth_sources,
        })

    # --- Roles ---
    for role in root.findall(f".//{_tag('Role')}"):
        model["roles"].append({
            "name": role.get("name", ""),
            "description": role.get("description", ""),
        })

    # --- Role Mappings ---
    for rm in root.findall(f".//{_tag('RoleMapping')}"):
        rules = []
        for i, rule_el in enumerate(rm.findall(f".//{_tag('Rule')}")):
            rules.append(_parse_rule(rule_el, i))
        model["roleMappings"].append({
            "name": rm.get("name", ""),
            "description": rm.get("description", ""),
            "ruleCombineAlgo": rm.get("ruleCombineAlgo", ""),
            "defaultRole": rm.get("dftRoleName", ""),
            "rules": rules,
        })

    # --- Enforcement Policies ---
    for ep in root.findall(f".//{_tag('EnforcementPolicy')}"):
        rules = []
        for i, rule_el in enumerate(ep.findall(f".//{_tag('Rule')}")):
            rules.append(_parse_rule(rule_el, i))
        policy_el = ep.find(f".//{_tag('Policy')}")
        rule_combine_algo = (
            policy_el.get("ruleCombiningAlgorithm", "first-applicable")
            if policy_el is not None else "first-applicable"
        )
        model["enforcementPolicies"].append({
            "name": ep.get("name", ""),
            "description": ep.get("description", ""),
            "policyType": ep.get("policyType", ""),
            "defaultProfile": ep.get("defaultProfileName", ""),
            "ruleCombineAlgo": rule_combine_algo,
            "rules": rules,
        })

    # --- RADIUS Enforcement Profiles ---
    for rp in root.findall(f".//{_tag('RadiusEnfProfile')}"):
        model["radiusEnfProfiles"].append({
            "name": rp.get("name", ""),
            "description": rp.get("description", ""),
            "action": rp.get("action", ""),
            "attributes": _attribute_list(rp) + _dur_attributes(rp),
            "product": rp.get("product", ""),          # e.g. "durPluginA" for DUR profiles
            "nadGroups": _string_list(rp, "NadGroupNameList"),
            "extras": _profile_extras(rp),
        })

    # --- Post-Auth Enforcement Profiles ---
    for pp in root.findall(f".//{_tag('PostAuthEnfProfile')}"):
        model["postAuthEnfProfiles"].append({
            "name": pp.get("name", ""),
            "description": pp.get("description", ""),
            "postAuthType": pp.get("postAuthType", ""),
            "attributes": _attribute_list(pp),
            "extras": _profile_extras(pp),
        })

    # --- TACACS Enforcement Profiles ---
    for tp in root.findall(f".//{_tag('TacacsEnfProfile')}"):
        model["tacacsEnfProfiles"].append({
            "name":         tp.get("name", ""),
            "description":  tp.get("description", ""),
            "action":       tp.get("action", ""),
            "autzStatus":   tp.get("autzStatus", ""),   # PASS_ADD | PASS_REPL | FAIL
            "maxPrivLevel": tp.get("maxPrivLevel", ""),  # "0"–"15" or ""
            "attributes":   _attribute_list(tp),
            "nadGroups":    _string_list(tp, "NadGroupNameList"),
            "extras": _profile_extras(tp),
        })

    # --- Radius CoA Enforcement Profiles ---
    for cp in root.findall(f".//{_tag('RadiusCoAEnfProfile')}"):
        model["radiusCoaEnfProfiles"].append({
            "name": cp.get("name", ""),
            "description": cp.get("description", ""),
            "action": cp.get("action", ""),
            "template": cp.get("template", ""),
            "attributes": _attribute_list(cp),
            "nadGroups": _string_list(cp, "NadGroupNameList"),
            "extras": _profile_extras(cp),
        })

    # --- Generic Enforcement Profiles ---
    for gp in root.findall(f".//{_tag('GenericEnfProfile')}"):
        model["genericEnfProfiles"].append({
            "name": gp.get("name", ""),
            "description": gp.get("description", ""),
            "action": gp.get("action", ""),
            "type": gp.get("type", ""),
            # Generic profiles carry <ProfileParams> instead of an AttributeList.
            "attributes": [
                {
                    "name": pp_el.get("name", ""),
                    "type": "",
                    "value": pp_el.get("value", ""),
                    "displayValue": pp_el.get("displayValue", ""),
                }
                for pp_el in gp.findall(_tag("ProfileParams"))
            ],
            "extras": _profile_extras(gp),
        })

    # --- Any other enforcement profile type (SNMP, Agent, HTTP, CLI, ...) ---
    # Captured generically so policies referencing them resolve to the real
    # profile (with its raw settings) instead of a "not in export" placeholder.
    model["otherEnfProfiles"] = []
    for el in root.iter():
        tag = _local(el.tag)
        if not tag.endswith("EnfProfile") or tag in _KNOWN_PROFILE_PARTS:
            continue
        model["otherEnfProfiles"].append({
            "name": el.get("name", ""),
            "description": el.get("description", ""),
            "action": el.get("action", ""),
            "elementType": tag,
            "attributes": _attribute_list(el),
            "nadGroups": _string_list(el, "NadGroupNameList"),
            "extras": _extras(el, {"name", "description", "action"}, {"AttributeList", "NadGroupNameList"}),
        })

    return model
