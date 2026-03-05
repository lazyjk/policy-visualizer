"""
Phase 4: Flow IR Compilation

Converts a PolicyIR Service into a directed graph of nodes and edges.
Follows first-applicable semantics:
- Role mapping rules form an ordered decision chain.
  Each YES branch sets the role and converges to the single enforcement chain.
- The enforcement chain is built once and shared across all role outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .normalizer import expr_to_label, expr_to_node_label
from .policy_ir import (
    ApplyProfiles,
    EnforcementPolicy,
    EnforcementProfile,
    PolicyIR,
    Service,
    SetRole,
)

NodeType = Literal["start", "process", "decision", "action", "end"]
EdgeLabel = Literal["", "YES", "NO", "FAIL", "PASS", "CONTINUE"]


@dataclass
class FlowNode:
    id: str
    type: NodeType
    label: str
    trace_rule_id: str = ""
    sub_label: str = ""
    rank_group: str = ""


@dataclass
class FlowEdge:
    from_id: str
    to_id: str
    label: EdgeLabel = ""
    reason: str = ""      # human-readable cause for conditional edges (e.g. "usernotfound")


@dataclass
class FlowIR:
    service_id: str
    service_name: str
    service_type: str = "RADIUS"
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)

    def add_node(self, node: FlowNode) -> FlowNode:
        self.nodes.append(node)
        return node

    def add_edge(self, from_id: str, to_id: str, label: EdgeLabel = "", reason: str = "") -> None:
        self.edges.append(FlowEdge(from_id=from_id, to_id=to_id, label=label, reason=reason))


_DENY_PROFILE_TYPES = {"radius_reject", "tacacs_other"}
_DENY_ACTIONS = {"deny", "reject"}


def _is_deny(
    profile_ids: list[str],
    profile_names: list[str],
    profiles: dict[str, EnforcementProfile],
) -> bool:
    """Return True if any profile in the list represents a deny/reject outcome.

    Resolution order:
    1. profile_type field ("radius_reject", "tacacs_other") — canonical
    2. action field ("deny", "reject") — secondary signal
    3. name heuristic — fallback for profiles not present in the IR dict
    """
    for pid, name in zip(profile_ids, profile_names):
        profile = profiles.get(pid)
        if profile is not None:
            if profile.profile_type in _DENY_PROFILE_TYPES:
                return True
            if profile.action.lower() in _DENY_ACTIONS:
                return True
        else:
            # Fallback: profile not in IR (should not happen post-fail-fast)
            if "deny" in name.lower():
                return True
    return False


def _profiles_label(profile_names: list[str]) -> str:
    return ", ".join(profile_names) if profile_names else "Apply profiles"


def compile_service(service: Service, ir: PolicyIR) -> FlowIR:
    flow = FlowIR(service_id=service.id, service_name=service.name, service_type=service.service_type)
    sid = service.id

    # -----------------------------------------------------------------------
    # Start
    # -----------------------------------------------------------------------
    start = flow.add_node(FlowNode(id=f"{sid}__start", type="start", label=service.name))

    # -----------------------------------------------------------------------
    # Service match decision
    # -----------------------------------------------------------------------
    match_label = expr_to_node_label(service.match)
    svc_match = flow.add_node(FlowNode(
        id=f"{sid}__match",
        type="decision",
        label=f"Service Match?\n{match_label}",
    ))
    flow.add_edge(start.id, svc_match.id)

    no_match_end = flow.add_node(FlowNode(
        id=f"{sid}__no_match",
        type="end",
        label="Skip\n(no match)",
    ))
    flow.add_edge(svc_match.id, no_match_end.id, "NO")

    # -----------------------------------------------------------------------
    # Authentication process
    # -----------------------------------------------------------------------
    method_names = service.authentication.method_names
    source_names = service.authentication.source_names
    auth_label = "Authenticate"
    if method_names:
        auth_label += "\nMethods: " + ", ".join(method_names)
    if source_names:
        auth_label += "\nSources: " + ", ".join(source_names)

    auth_node = flow.add_node(FlowNode(id=f"{sid}__auth", type="process", label=auth_label))
    flow.add_edge(svc_match.id, auth_node.id, "YES")

    auth_fail = flow.add_node(FlowNode(
        id=f"{sid}__auth_fail",
        type="end",
        label="Auth Failed",
        sub_label="Access: DENY",
    ))
    flow.add_edge(auth_node.id, auth_fail.id, "FAIL")

    # -----------------------------------------------------------------------
    # Build enforcement chain (shared by all role paths)
    # -----------------------------------------------------------------------
    ep = ir.enforcement_policies.get(service.enforcement_policy_id)
    if ep is None:
        ep = next(
            (v for v in ir.enforcement_policies.values()
             if v.name == service.enforcement_policy_name),
            None,
        )

    # First node of the enforcement chain (all role paths will point here)
    enf_entry_id: str

    if ep is None or not ep.rules:
        deny_end = flow.add_node(FlowNode(
            id=f"{sid}__enf_no_policy",
            type="end",
            label="Access: DENY\n(no enforcement policy)",
        ))
        enf_entry_id = deny_end.id
    else:
        # Build each enforcement rule as a decision node
        first_enf_id = f"{sid}__enf_rule_0"
        enf_entry_id = first_enf_id

        prev_enf_id: str | None = None
        for rule in ep.rules:
            cond_label = expr_to_node_label(rule.when)
            dec = flow.add_node(FlowNode(
                id=f"{sid}__enf_rule_{rule.index}",
                type="decision",
                label=cond_label,
                trace_rule_id=rule.id,
                rank_group="enf_chain",
            ))
            if prev_enf_id is not None:
                flow.add_edge(prev_enf_id, dec.id, "NO")

            # YES → action → end
            if isinstance(rule.then, ApplyProfiles):
                names = rule.then.profile_names
                deny = _is_deny(rule.then.profile_ids, names, ir.enforcement_profiles)
                action = flow.add_node(FlowNode(
                    id=f"{sid}__enf_action_{rule.index}",
                    type="action",
                    label=_profiles_label(names),
                    trace_rule_id=rule.id,
                ))
                flow.add_edge(dec.id, action.id, "YES")
                access = "DENY" if deny else "ALLOW"
                end_node = flow.add_node(FlowNode(
                    id=f"{sid}__enf_end_{rule.index}",
                    type="end",
                    label=f"Access: {access}",
                ))
                flow.add_edge(action.id, end_node.id)

            prev_enf_id = dec.id

        # Enforcement default (last NO path)
        if ep.default is not None and isinstance(ep.default, ApplyProfiles):
            def_names = ep.default.profile_names
            deny = _is_deny(ep.default.profile_ids, def_names, ir.enforcement_profiles)
            def_action = flow.add_node(FlowNode(
                id=f"{sid}__enf_default_action",
                type="action",
                label=f"Default:\n{_profiles_label(def_names)}",
            ))
            flow.add_edge(prev_enf_id, def_action.id, "NO")  # type: ignore[arg-type]
            access = "DENY" if deny else "ALLOW"
            def_end = flow.add_node(FlowNode(
                id=f"{sid}__enf_default_end",
                type="end",
                label=f"Access: {access}\n(default)",
            ))
            flow.add_edge(def_action.id, def_end.id)
        elif prev_enf_id:
            implicit_deny = flow.add_node(FlowNode(
                id=f"{sid}__enf_implicit_deny",
                type="end",
                label="Access: DENY\n(implicit)",
            ))
            flow.add_edge(prev_enf_id, implicit_deny.id, "NO")

    # -----------------------------------------------------------------------
    # Role mapping decision chain → all YES branches converge to enf_entry_id
    # -----------------------------------------------------------------------
    rm = ir.role_mapping_policies.get(service.role_mapping_policy_id)
    if rm is None:
        rm = next(
            (v for v in ir.role_mapping_policies.values()
             if v.name == service.role_mapping_policy_name),
            None,
        )

    current_tail = auth_node.id
    current_label = "PASS"

    if rm is not None:
        for rule in rm.rules:
            cond_label = expr_to_node_label(rule.when)
            dec = flow.add_node(FlowNode(
                id=f"{sid}__rm_rule_{rule.index}",
                type="decision",
                label=cond_label,
                trace_rule_id=rule.id,
                rank_group="rm_chain",
            ))
            flow.add_edge(current_tail, dec.id, current_label)

            if isinstance(rule.then, SetRole):
                role_action = flow.add_node(FlowNode(
                    id=f"{sid}__rm_action_{rule.index}",
                    type="action",
                    label=f"Set Role:\n{rule.then.role_name}",
                    trace_rule_id=rule.id,
                ))
                flow.add_edge(dec.id, role_action.id, "YES")
                # Converge to the shared enforcement chain
                flow.add_edge(role_action.id, enf_entry_id)

            current_tail = dec.id
            current_label = "NO"

        # Default role → enforcement
        if rm.default is not None:
            def_role = flow.add_node(FlowNode(
                id=f"{sid}__rm_default",
                type="action",
                label=f"Default Role:\n{rm.default.role_name}",
            ))
            flow.add_edge(current_tail, def_role.id, current_label)
            flow.add_edge(def_role.id, enf_entry_id)
        else:
            no_role_end = flow.add_node(FlowNode(
                id=f"{sid}__no_role",
                type="end",
                label="Access: DENY\n(no role matched)",
            ))
            flow.add_edge(current_tail, no_role_end.id, current_label)
    else:
        # No role mapping — go straight to enforcement
        flow.add_edge(current_tail, enf_entry_id, current_label)

    return flow
