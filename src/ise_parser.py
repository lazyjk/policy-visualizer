"""
ISE XML Parser

Parses a Cisco ISE policy export XML file into a raw ISE object model.
The export contains radiusPolicySets, tacacsPolicySets, libraryConditions,
and AznResults (profiles).

Entry point: ise_parse(xml_path) -> dict
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET


def ise_parse(xml_path: str | Path) -> dict:
    """Parse an ISE XML export and return the raw ISE object model."""
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    library = _parse_library_conditions(root)
    profiles = _parse_profiles(root)
    policy_sets = _parse_policy_sets(root)

    return {
        "format": "ise",
        "policy_sets": policy_sets,
        "library_conditions": library,
        "profiles": profiles,
    }


# ---------------------------------------------------------------------------
# Library conditions
# ---------------------------------------------------------------------------

def _parse_library_conditions(root) -> dict[str, dict]:
    """Return {name: {id, name, description, condition}} from all libraryConditions."""
    library: dict[str, dict] = {}
    for lc_container in root.findall("libraryConditions"):
        for lc in lc_container.findall("libraryCondition"):
            name = _text(lc, "name", "")
            if not name:
                continue
            cond_el = lc.find("condition")
            library[name] = {
                "id": _text(lc, "id", ""),
                "name": name,
                "description": _text(lc, "description", ""),
                "condition": _parse_condition(cond_el),
            }
    return library


# ---------------------------------------------------------------------------
# Profiles (AznResults)
# ---------------------------------------------------------------------------

def _parse_profiles(root) -> dict[str, dict]:
    """Return {name: {name, description, profile_type, access_type}} from AznResults."""
    profiles: dict[str, dict] = {}
    azn = root.find("AznResults")
    if azn is None:
        return profiles

    std = azn.find("StandardResults")
    if std is not None:
        for p in std.findall("Profile"):
            name = p.get("name", "")
            if not name:
                continue
            access_type = None
            for opt in p.findall("option"):
                if opt.get("name") == "Access Type":
                    access_type = opt.get("value")
            if name not in profiles:
                profiles[name] = {
                    "name": name,
                    "description": p.get("description", ""),
                    "profile_type": "standard",
                    "access_type": access_type,
                }

    tacacs_profiles = azn.find("TacacsProfile")
    if tacacs_profiles is not None:
        for p in tacacs_profiles.findall("TacacsProfile"):
            name = p.get("name", "")
            if not name:
                continue
            if name not in profiles:
                profiles[name] = {
                    "name": name,
                    "description": p.get("description", ""),
                    "profile_type": "tacacs",
                    "access_type": None,
                }

    commandsets = azn.find("TacacsCommandset")
    if commandsets is not None:
        for cs in commandsets.findall("TacacsCommandset"):
            name = cs.get("name", "")
            if not name:
                continue
            if name not in profiles:
                profiles[name] = {
                    "name": name,
                    "description": cs.get("description", ""),
                    "profile_type": "commandset",
                    "access_type": None,
                }

    return profiles


# ---------------------------------------------------------------------------
# Policy sets
# ---------------------------------------------------------------------------

def _parse_policy_sets(root) -> list[dict]:
    sets: list[dict] = []
    policysets = root.find("policysets")
    if policysets is None:
        return sets

    radius_container = policysets.find("radiusPolicySets")
    if radius_container is not None:
        for ps in radius_container.findall("radiusPolicySet"):
            sets.append(_parse_policy_set(ps, "RADIUS"))

    tacacs_container = policysets.find("tacacsPolicySets")
    if tacacs_container is not None:
        for ps in tacacs_container.findall("tacacsPolicySet"):
            sets.append(_parse_policy_set(ps, "TACACS"))

    # Sort by rank so order is deterministic
    sets.sort(key=lambda s: s["rank"])
    return sets


def _parse_policy_set(ps_el, set_type: str) -> dict:
    cond_el = ps_el.find("condition")
    authen_rules = [
        _parse_authen_rule(r, idx)
        for idx, r in enumerate(ps_el.findall("authenRules"))
    ]
    author_rules = [
        _parse_author_rule(r, idx)
        for idx, r in enumerate(ps_el.findall("authorRules"))
    ]
    return {
        "id": _text(ps_el, "id", ""),
        "name": _text(ps_el, "name", ""),
        "description": _text(ps_el, "description", ""),
        "rank": _int(ps_el, "rank", 0),
        "status": _text(ps_el, "status", "ENABLED"),
        "set_type": set_type,
        "allowed_protocols": _text(ps_el, "allowedProtocols", ""),
        "match_condition": _parse_condition(cond_el),
        "authen_rules": authen_rules,
        "author_rules": author_rules,
    }


def _parse_authen_rule(r_el, default_rank: int) -> dict:
    cond_el = r_el.find("condition")
    return {
        "id": _text(r_el, "id", ""),
        "name": _text(r_el, "name", ""),
        "rank": _int(r_el, "rank", default_rank),
        "status": _text(r_el, "status", "ENABLED"),
        "condition": _parse_condition(cond_el),
        "storetype": _text(r_el, "storetype", ""),
        "storename": _text(r_el, "storename", ""),
        "authen_fail_action": _text(r_el, "authenfailaction", "REJECT"),
        "user_not_found_action": _text(r_el, "usernotfoundaction", "REJECT"),
        "process_fail_action": _text(r_el, "processfailaction", "DROP"),
    }


def _parse_author_rule(r_el, default_rank: int) -> dict:
    cond_el = r_el.find("condition")
    profiles = [el.text.strip() for el in r_el.findall("profiles") if el.text and el.text.strip()]
    commandsets = [el.text.strip() for el in r_el.findall("commandsets") if el.text and el.text.strip()]
    groups = [el.text.strip() for el in r_el.findall("groups") if el.text and el.text.strip()]
    return {
        "id": _text(r_el, "id", ""),
        "name": _text(r_el, "name", ""),
        "rank": _int(r_el, "rank", default_rank),
        "status": _text(r_el, "status", "ENABLED"),
        "condition": _parse_condition(cond_el),
        "profiles": profiles,
        "commandsets": commandsets,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Condition tree parsing
# ---------------------------------------------------------------------------

def _parse_condition(cond_el) -> dict | None:
    """Parse a <condition> element into a raw condition dict, or None for match-all."""
    if cond_el is None:
        return None
    # Self-closing empty element: <condition/> has no children and no text
    if len(cond_el) == 0 and not (cond_el.text and cond_el.text.strip()):
        return None
    type_el = cond_el.find("type")
    if type_el is None or not type_el.text:
        return None
    return _parse_condition_node(cond_el)


def _parse_condition_node(node) -> dict | None:
    """Recursively parse a condition node (AND_BLOCK, OR_BLOCK, SINGLE, REFERENCE)."""
    type_el = node.find("type")
    if type_el is None or not type_el.text:
        return None
    node_type = type_el.text.strip()
    is_not_el = node.find("isNot")
    is_not = (is_not_el is not None and is_not_el.text and is_not_el.text.strip().lower() == "true")

    if node_type == "SINGLE":
        return {
            "type": "SINGLE",
            "is_not": is_not,
            "lhs_attribute": _child_text(node, "lhsAttribute", ""),
            "lhs_dictionary": _child_text(node, "lhsDictionary", ""),
            "rhs_attribute": _child_text(node, "rhsAttribute", ""),
            "rhs_dictionary": _child_text(node, "rhsDictionary", ""),
            "operator": _child_text(node, "operator", ""),
        }

    if node_type == "REFERENCE":
        return {
            "type": "REFERENCE",
            "is_not": is_not,
            "ref_id": _child_text(node, "refId", ""),
        }

    if node_type in ("AND_BLOCK", "OR_BLOCK"):
        children = []
        for child in node.findall("children"):
            parsed = _parse_condition_node(child)
            if parsed is not None:
                children.append(parsed)
        return {
            "type": node_type,
            "is_not": is_not,
            "children": children,
        }

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(el, tag: str, default: str = "") -> str:
    child = el.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _child_text(el, tag: str, default: str = "") -> str:
    child = el.find(tag)
    if child is None:
        return default
    return (child.text or "").strip()


def _int(el, tag: str, default: int = 0) -> int:
    val = _text(el, tag, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default
