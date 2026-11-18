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
    from .policy_ir import EnforcementProfile, PolicyIR, Service


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
    profiles: list[dict] | None = None,
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
        "profiles": profiles or [],
    }


def _profile_detail(profile: "EnforcementProfile") -> dict:
    return {
        "name": profile.name,
        "profile_type": profile.profile_type,
        "action": profile.action,
        "template": profile.template,
        "product": profile.product,
        "nad_groups": list(profile.nad_groups),
        "element_type": profile.element_type,
        "extras": _extras_detail(profile.extras),
        "attributes": [
            {
                "name": a.name,
                "type": a.type,
                "value": a.value,
                "display_value": a.display_value,
            }
            for a in profile.attributes
        ],
    }


def _extras_detail(extras) -> list[dict]:
    return [{"path": e.path, "value": e.value} for e in extras]


def uninterpreted_notes(service: "Service", ir: "PolicyIR") -> list[str]:
    """Service-scoped warnings for settings shown raw ("Other settings").

    Covers the service itself and every enforcement profile its enforcement
    policy can apply (rules + default), in rule order, de-duplicated.
    """
    from .policy_ir import ApplyProfiles

    notes: list[str] = []
    if service.extras:
        notes.append(
            f"Service '{service.name}' has {len(service.extras)} setting(s) this version "
            "does not interpret — shown under 'Other settings' in the inspector."
        )
    ep = ir.enforcement_policies.get(service.enforcement_policy_id)
    if ep is None:
        return notes
    thens = [r.then for r in ep.rules] + ([ep.default] if ep.default is not None else [])
    seen: set[str] = set()
    for then in thens:
        if not isinstance(then, ApplyProfiles):
            continue
        for pid in then.profile_ids:
            prof = ir.enforcement_profiles.get(pid)
            if prof is None or pid in seen:
                continue
            seen.add(pid)
            if prof.profile_type == "other":
                notes.append(
                    f"Enforcement profile '{prof.name}' is a {prof.element_type or 'profile'} type this "
                    "version does not model — its raw settings are shown in the inspector."
                )
            elif prof.extras:
                notes.append(
                    f"Enforcement profile '{prof.name}' has {len(prof.extras)} setting(s) this version "
                    "does not interpret — shown under 'Other settings' in the inspector."
                )
    return notes


def _profile_details(profile_ids: list[str], ir: "PolicyIR") -> list[dict]:
    """Resolve profile IDs to detail dicts, preserving rule order."""
    out = []
    for pid in profile_ids:
        prof = ir.enforcement_profiles.get(pid)
        if prof is not None:
            out.append(_profile_detail(prof))
    return out


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
        "enabled": service.enabled,
        "template": service.template,
        "monitor_mode": service.monitor_mode,
        "use_cached_results": service.use_cached_results,
        "posture_enabled": service.posture_enabled,
        "profiler_enabled": service.profiler_enabled,
        "audit_enabled": service.audit_enabled,
        "role_mapping_policy_name": service.role_mapping_policy_name,
        "enforcement_policy_name": service.enforcement_policy_name,
        "extras": _extras_detail(service.extras),
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
            profiles: list[dict] = []
            if isinstance(then, ApplyProfiles):
                names = then.profile_names if then.profile_names else then.profile_ids
                action_text = ", ".join(names)
                linked = list(names)
                profiles = _profile_details(then.profile_ids, ir)
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
                    profiles=profiles,
                )
            )

    # Enforcement default (keyed by the default action node's trace_rule_id)
    enforcement_default: dict | None = None
    if enf_policy and enf_policy.rules and enf_policy.default is not None:
        from .flow_ir import default_trace_id
        from .policy_ir import ApplyProfiles
        if isinstance(enf_policy.default, ApplyProfiles):
            d = enf_policy.default
            names = d.profile_names if d.profile_names else d.profile_ids
            dtid = default_trace_id(enf_policy.id)
            enforcement_default = _rule_detail(
                rule_id=dtid,
                node_trace_id=dtid,
                index=len(enf_policy.rules),
                name="Default",
                condition_text="(no rule matched)",
                action_text=", ".join(names),
                on_match="stop",
                linked_names=list(names),
                profiles=_profile_details(d.profile_ids, ir),
            )

    rule_index = _build_rule_index([], role_mapping_rules, enforcement_rules)
    if enforcement_default is not None:
        rule_index[enforcement_default["node_trace_id"]] = enforcement_default

    svc_match_key = f"{service.id}__match"
    rule_index[svc_match_key] = _rule_detail(
        rule_id=svc_match_key,
        node_trace_id=svc_match_key,
        index=0,
        name="Service Match",
        condition_text=condition_to_text(service.match),
        action_text="Proceed to authentication",
        on_match="stop",
        linked_names=[],
    )

    return {
        "service_context": service_context,
        "authen_rules": [],
        "role_mapping_rules": role_mapping_rules,
        "enforcement_rules": enforcement_rules,
        "enforcement_default": enforcement_default,
        "warnings": list(ir.warnings) + uninterpreted_notes(service, ir),
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

    if ps.match is not None:
        ps_match_key = f"{ps.id}__match"
        rule_index[ps_match_key] = _rule_detail(
            rule_id=ps_match_key,
            node_trace_id=ps_match_key,
            index=0,
            name="Policy Set Match",
            condition_text=condition_to_text(ps.match),
            action_text="Proceed to authentication",
            on_match="stop",
            linked_names=[],
        )

    return {
        "service_context": service_context,
        "authen_rules": authen_rules,
        "role_mapping_rules": [],
        "enforcement_rules": enforcement_rules,
        "warnings": list(ir.warnings),
        "rule_index": rule_index,
    }
