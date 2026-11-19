"""
ClearPass rules-engine XML (as stored in tipsdb) -> raw rule dicts.

The DB keeps conditions as Avenda rules-engine XML in
  tips_service.rule_xml            (one <Rule>: the service match)
  tips_role_mapping_policy.policy_xml   (<Policy RuleCombiningAlgId=...><Rule>...)
  tips_enf_policy.policy_xml            (same)

This module converts them into exactly the shapes src/parser.py produces from
an XML export (`_rule_expressions` / `_parse_rule`), so policy_ir.build() and
everything downstream are shared between the two inputs.

Format notes (verified against a lab DB and its XML export):
- <Attribute AttributeId="Radius:IETF:NAS-Port-Type" Operator=... AttributeValue=...
  AttributeValueDispName=...>. The attribute name is the part after the LAST
  colon; the rest is the namespace ("Radius:IETF", "Authorization:[Source]").
- <Expression Operator="and"> = match ALL. A missing Operator corresponds to
  the export's operator="OR" / MATCHES_ANY. Every observed case has a single
  predicate, so a multi-predicate expression without an Operator is converted
  as OR but reported with a warning.
- Service rules are stored as and(<user expression>, Connection:Protocol = X).
  The protocol test is implicit (derived from the service type) and is not
  shown in the export, so it is dropped here.
- <Result AttributeId="Tips:Role" | "Tips:Enforcement-Profile" AttributeValue="<ids>">
  carries object IDs (comma-separated); names are resolved via id maps.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

_PROTOCOL_ATTRIBUTE = "Connection:Protocol"

# Rules-engine result AttributeId -> (export RuleResult name, type)
_RESULT_NAMES = {
    "Tips:Role": ("Role", "Tips"),
    "Tips:Enforcement-Profile": ("Enforcement-Profile", "Tips"),
}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _split_attribute_id(attribute_id: str) -> tuple[str, str]:
    """'Radius:IETF:NAS-Port-Type' -> ('Radius:IETF', 'NAS-Port-Type')."""
    ns, sep, name = attribute_id.rpartition(":")
    return (ns, name) if sep else ("", attribute_id)


def _attribute(el: ET.Element) -> dict[str, str]:
    ns, name = _split_attribute_id(el.get("AttributeId", ""))
    value = el.get("AttributeValue", "")
    return {
        "name": name,
        "type": ns,
        "operator": el.get("Operator", ""),
        "value": value,
        "displayValue": el.get("AttributeValueDispName", value),
    }


def _expression(expr: ET.Element, warnings: list[str], context: str) -> dict[str, Any]:
    """Flatten an <Expression> into the export's single-level shape."""
    op = (expr.get("Operator") or "").strip().lower()
    attrs = [_attribute(a) for a in _children(expr, "Attribute")]
    for sub in _children(expr, "Expression"):
        sub_op = (sub.get("Operator") or "").strip().lower()
        nested = _expression(sub, warnings, context)
        if sub_op and op and sub_op != op and len(nested["attributes"]) > 1:
            warnings.append(
                f"{context}: nested '{sub_op}' group inside '{op}' was flattened — "
                "check this condition in ClearPass"
            )
        attrs.extend(nested["attributes"])
    if not op and len(attrs) > 1:
        warnings.append(
            f"{context}: condition has {len(attrs)} predicates but no AND/OR operator — "
            "shown as match ANY"
        )
    if op == "and":
        return {"operator": "and", "displayOperator": "MATCHES_ALL", "attributes": attrs}
    return {"operator": "OR", "displayOperator": "MATCHES_ANY", "attributes": attrs}


def _parse_xml(text: str, warnings: list[str], context: str) -> ET.Element | None:
    if not text or not text.strip():
        return None
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        warnings.append(f"{context}: rule XML could not be read ({exc}) — rule skipped")
        return None


def service_match(rule_xml: str | None, warnings: list[str], context: str) -> dict[str, Any] | None:
    """tips_service.rule_xml -> the export's matchExpression (None = match all)."""
    root = _parse_xml(rule_xml or "", warnings, context)
    if root is None:
        return None
    rule = root if _local(root.tag) == "Rule" else next((e for e in root.iter() if _local(e.tag) == "Rule"), None)
    cond = next(iter(_children(rule, "Condition")), None) if rule is not None else None
    outer = next(iter(_children(cond, "Expression")), None) if cond is not None else None
    if outer is None:
        return None
    # Drop the implicit top-level protocol test; keep the user's expression.
    user_parts = [
        c for c in outer
        if not (_local(c.tag) == "Attribute" and c.get("AttributeId") == _PROTOCOL_ATTRIBUTE)
    ]
    if not user_parts:
        return None
    if len(user_parts) == 1 and _local(user_parts[0].tag) == "Expression":
        expr = _expression(user_parts[0], warnings, context)
    else:
        # Unexpected layout: keep everything except the protocol test under the outer operator.
        wrapper = ET.Element("Expression", dict(outer.attrib))
        wrapper.extend(user_parts)
        expr = _expression(wrapper, warnings, context)
    return expr if expr["attributes"] else None


def policy_rules(
    policy_xml: str | None,
    warnings: list[str],
    context: str,
    names_by_id: dict[str, dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Role-mapping / enforcement policy XML -> (ruleCombineAlgo, raw rules).

    `names_by_id` maps a result AttributeId ("Tips:Role", "Tips:Enforcement-Profile")
    to {object id: name}; results become comma-joined names like the export's
    displayValue. Unknown IDs fall back to the stored display name.
    """
    root = _parse_xml(policy_xml or "", warnings, context)
    if root is None:
        return "first-applicable", []
    algo = root.get("RuleCombiningAlgId") or "first-applicable"
    names_by_id = names_by_id or {}
    rules: list[dict[str, Any]] = []
    for index, rule in enumerate(_children(root, "Rule")):
        cond = next(iter(_children(rule, "Condition")), None)
        expr_el = next(iter(_children(cond, "Expression")), None) if cond is not None else None
        rule_ctx = f"{context} rule {index + 1}"
        expression = _expression(expr_el, warnings, rule_ctx) if expr_el is not None else None
        results = []
        for res in _children(rule, "Result"):
            attr_id = res.get("AttributeId", "")
            name, rtype = _RESULT_NAMES.get(attr_id, _split_attribute_id(attr_id)[::-1])
            value = res.get("AttributeValue", "")
            display = res.get("AttributeValueDispName", value)
            lookup = names_by_id.get(attr_id)
            if lookup:
                ids = [v.strip() for v in value.split(",") if v.strip()]
                if ids and all(i in lookup for i in ids):
                    display = ", ".join(lookup[i] for i in ids)
            results.append({"name": name, "type": rtype, "value": value, "displayValue": display})
        rules.append({"index": index, "expression": expression, "results": results})
    return algo, rules
