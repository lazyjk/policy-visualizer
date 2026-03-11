"""
Policy Details Serializer

Converts compiled PolicyIR / ISEPolicyIR objects into a structured details
payload suitable for the inspector UI and PDF appendix export.

Entry points:
  build_clearpass_details(service, ir) -> dict
  build_ise_details(ps, ir) -> dict

Both return a plain dict matching the PolicyDetailsSchema shape defined in
api/schemas.py.  The caller (api/routes/flow.py) is responsible for wrapping
the dict in a Pydantic model.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .normalizer import BooleanExpr, expr_to_node_label

if TYPE_CHECKING:
    from .ise_policy_ir import ISEPolicyIR, ISEPolicySet
    from .policy_ir import PolicyIR, Service


def condition_to_text(expr: BooleanExpr | None) -> str:
    """Render a canonical BooleanExpr as a human-readable multiline string.

    Delegates to expr_to_node_label which already handles:
    - None  → "(no condition)"
    - Predicate → attribute / operator / value lines
    - And / Or  → predicates with --- AND --- / --- OR --- separators
    - Not       → NOT prefix
    """
    return expr_to_node_label(expr)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rule_detail(
    rule_id: str,
    node_trace_id: str,
    index: int,
    name: str,
    condition_text: str,
    action_text: str,
    on_match: str,
    linked_names: list[str],
) -> dict:
    return {
        "rule_id": rule_id,
        "node_trace_id": node_trace_id,
        "index": index,
        "name": name,
        "condition_text": condition_text,
        "action_text": action_text,
        "on_match": on_match,
        "linked_names": linked_names,
    }


def _build_rule_index(
    authen_rules: list[dict],
    role_mapping_rules: list[dict],
    enforcement_rules: list[dict],
) -> dict[str, dict]:
    """Build a trace_rule_id → RuleDetail lookup dict from all rule lists."""
    index: dict[str, dict] = {}
    for rule in authen_rules + role_mapping_rules + enforcement_rules:
        tid = rule["node_trace_id"]
        if tid:
            index[tid] = rule
    return index


# ---------------------------------------------------------------------------
# ClearPass details builder
# ---------------------------------------------------------------------------

def build_clearpass_details(service: "Service", ir: "PolicyIR") -> dict:
    """Serialize a ClearPass service + PolicyIR into a PolicyDetailsSchema dict."""
    # Service context
    service_context = {
        "service_name": service.name,
        "service_type": service.service_type,
        "description": service.description,
        "auth_method_names": list(service.authentication.method_names),
        "auth_source_names": list(service.authentication.source_names),
        "condition_text": condition_to_text(service.match),
    }

    # Role mapping rules (ordered by index)
    role_mapping_rules: list[dict] = []
    rm_policy = ir.role_mapping_policies.get(service.role_mapping_policy_id)
    if rm_policy:
        for rule in sorted(rm_policy.rules, key=lambda r: r.index):
            from .policy_ir import SetRole
            then = rule.then
            if isinstance(then, SetRole):
                action_text = f"Set Role: {then.role_name}" if then.role_name else f"Set Role: {then.role_id}"
                linked = [then.role_name] if then.role_name else [then.role_id]
            else:
                # ApplyProfiles (unexpected in role mapping, but handle gracefully)
                names = getattr(then, "profile_names", []) or getattr(then, "profile_ids", [])
                action_text = ", ".join(names)
                linked = list(names)
            role_mapping_rules.append(
                _rule_detail(
                    rule_id=rule.id,
                    node_trace_id=rule.id,
                    index=rule.index,
                    name=rm_policy.name,
                    condition_text=condition_to_text(rule.when),
                    action_text=action_text,
                    on_match=rule.flow.on_match,
                    linked_names=linked,
                )
            )

    # Enforcement rules (ordered by index)
    enforcement_rules: list[dict] = []
    enf_policy = ir.enforcement_policies.get(service.enforcement_policy_id)
    if enf_policy:
        for rule in sorted(enf_policy.rules, key=lambda r: r.index):
            from .policy_ir import ApplyProfiles
            then = rule.then
            if isinstance(then, ApplyProfiles):
                names = then.profile_names if then.profile_names else then.profile_ids
                action_text = ", ".join(names)
                linked = list(names)
            else:
                action_text = str(then)
                linked = []
            enforcement_rules.append(
                _rule_detail(
                    rule_id=rule.id,
                    node_trace_id=rule.id,
                    index=rule.index,
                    name=enf_policy.name,
                    condition_text=condition_to_text(rule.when),
                    action_text=action_text,
                    on_match=rule.flow.on_match,
                    linked_names=linked,
                )
            )

    rule_index = _build_rule_index([], role_mapping_rules, enforcement_rules)

    return {
        "service_context": service_context,
        "authen_rules": [],
        "role_mapping_rules": role_mapping_rules,
        "enforcement_rules": enforcement_rules,
        "warnings": list(ir.warnings),
        "rule_index": rule_index,
    }


# ---------------------------------------------------------------------------
# ISE details builder
# ---------------------------------------------------------------------------

def build_ise_details(ps: "ISEPolicySet", ir: "ISEPolicyIR") -> dict:
    """Serialize an ISEPolicySet + ISEPolicyIR into a PolicyDetailsSchema dict."""
    # Service context (policy set level)
    service_context = {
        "service_name": ps.name,
        "service_type": ps.set_type,
        "description": ps.description,
        "auth_method_names": [],
        "auth_source_names": [],
        "condition_text": condition_to_text(ps.match),
    }

    # Authentication rules (ordered by index)
    authen_rules: list[dict] = []
    for rule in sorted(ps.authen_rules, key=lambda r: r.index):
        store_desc = rule.storename
        if rule.storetype:
            store_desc = f"{rule.storename} ({rule.storetype})"
        on_match = "continue" if rule.user_not_found_action == "CONTINUE" else "stop"
        authen_rules.append(
            _rule_detail(
                rule_id=rule.id,
                node_trace_id=rule.id,
                index=rule.index,
                name=rule.name,
                condition_text=condition_to_text(rule.when),
                action_text=f"Auth: {store_desc}",
                on_match=on_match,
                linked_names=[rule.storename] if rule.storename else [],
            )
        )

    # Authorization rules → enforcement_rules (ordered by index)
    enforcement_rules: list[dict] = []
    for rule in sorted(ps.author_rules, key=lambda r: r.index):
        all_names = rule.profile_names + rule.commandset_names + rule.security_groups
        action_text = ", ".join(all_names) if all_names else "(no profiles)"
        enforcement_rules.append(
            _rule_detail(
                rule_id=rule.id,
                node_trace_id=rule.id,
                index=rule.index,
                name=rule.name,
                condition_text=condition_to_text(rule.when),
                action_text=action_text,
                on_match="stop",
                linked_names=list(all_names),
            )
        )

    rule_index = _build_rule_index(authen_rules, [], enforcement_rules)

    return {
        "service_context": service_context,
        "authen_rules": authen_rules,
        "role_mapping_rules": [],
        "enforcement_rules": enforcement_rules,
        "warnings": list(ir.warnings),
        "rule_index": rule_index,
    }
