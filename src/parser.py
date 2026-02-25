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
    }

    # --- RADIUS Services ---
    for svc in root.findall(f".//{_tag('RadiusEnforcementService')}"):
        expr_el = svc.find(f".//{_tag('RuleExpression')}")
        model["services"].append({
            "name": svc.get("name", ""),
            "description": svc.get("description", ""),
            "enabled": svc.get("enabled", "true"),
            "serviceType": "RADIUS",
            "serviceTemplate": (svc.findtext(_tag("ServiceTemplate")) or "").strip(),
            "matchExpression": _rule_expressions(expr_el),
            "authMethods": _string_list(svc, "AuthMethodNameList"),
            "authSources": _string_list(svc, "AuthSourceNameList"),
            "autzSources": _string_list(svc, "AutzSourceNameList"),
            "roleMappings": _string_list(svc, "RoleMappingNameList"),
            "enfPolicies": _string_list(svc, "EnfPolicyNameList"),
        })

    # --- TACACS Services ---
    for svc in root.findall(f".//{_tag('TacacsEnforcementService')}"):
        expr_el = svc.find(f".//{_tag('RuleExpression')}")
        model["services"].append({
            "name": svc.get("name", ""),
            "description": svc.get("description", ""),
            "enabled": svc.get("enabled", "true"),
            "serviceType": "TACACS",
            "serviceTemplate": (svc.findtext(_tag("ServiceTemplate")) or "").strip(),
            "matchExpression": _rule_expressions(expr_el),
            "authMethods": _string_list(svc, "AuthMethodNameList"),
            "authSources": _string_list(svc, "AuthSourceNameList"),
            "autzSources": _string_list(svc, "AutzSourceNameList"),
            "roleMappings": _string_list(svc, "RoleMappingNameList"),
            "enfPolicies": _string_list(svc, "EnfPolicyNameList"),
        })

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
        model["enforcementPolicies"].append({
            "name": ep.get("name", ""),
            "description": ep.get("description", ""),
            "policyType": ep.get("policyType", ""),
            "defaultProfile": ep.get("defaultProfileName", ""),
            "rules": rules,
        })

    # --- RADIUS Enforcement Profiles ---
    for rp in root.findall(f".//{_tag('RadiusEnfProfile')}"):
        model["radiusEnfProfiles"].append({
            "name": rp.get("name", ""),
            "description": rp.get("description", ""),
            "action": rp.get("action", ""),
        })

    # --- Post-Auth Enforcement Profiles ---
    for pp in root.findall(f".//{_tag('PostAuthEnfProfile')}"):
        attrs = []
        for a in pp.findall(f".//{_tag('Attribute')}"):
            attrs.append({
                "name": a.get("name", ""),
                "type": a.get("type", ""),
                "value": a.get("value", ""),
                "displayValue": a.get("displayValue", ""),
            })
        model["postAuthEnfProfiles"].append({
            "name": pp.get("name", ""),
            "description": pp.get("description", ""),
            "postAuthType": pp.get("postAuthType", ""),
            "attributes": attrs,
        })

    # --- TACACS Enforcement Profiles ---
    for tp in root.findall(f".//{_tag('TacacsEnfProfile')}"):
        model["tacacsEnfProfiles"].append({
            "name": tp.get("name", ""),
            "description": tp.get("description", ""),
            "action": tp.get("action", ""),
        })

    return model
