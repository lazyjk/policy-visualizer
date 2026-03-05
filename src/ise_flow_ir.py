"""
ISE Flow IR Compiler

Compiles an ISEPolicySet into a FlowIR directed graph using the same
FlowNode/FlowEdge/FlowIR types as the ClearPass flow compiler.

ISE flow structure (per policy set):
  START
   → [DECISION: match condition]  (skipped if match-all)
       YES → authen chain
       NO  → END (no match)
   authen chain: ordered decision+process pairs per authenRule
       process PASS → authz chain entry
       process FAIL → END (auth failed)
       process CONTINUE → next authen rule (if usernotfoundaction=CONTINUE)
       decision NO → next authen rule
   authz chain: ordered decision+action pairs per authorRule
       action → END (ACCEPT or DENY based on profile access_type)
       last NO → END (implicit deny)

Entry point: ise_compile_policy_set(ps, ir) -> FlowIR
"""
from __future__ import annotations

from .flow_ir import EdgeLabel, FlowEdge, FlowIR, FlowNode
from .ise_policy_ir import ISEAuthenRule, ISEAuthorRule, ISEPolicyIR, ISEPolicySet
from .normalizer import expr_to_node_label


def ise_compile_policy_set(ps: ISEPolicySet, ir: ISEPolicyIR) -> FlowIR:
    psid = ps.id
    flow = FlowIR(service_id=psid, service_name=ps.name, service_type=ps.set_type)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------
    start = flow.add_node(FlowNode(id=f"{psid}__start", type="start", label=ps.name))

    # ------------------------------------------------------------------
    # Policy set match condition (skip node entirely if match-all)
    # ------------------------------------------------------------------
    if ps.match is not None:
        match_label = expr_to_node_label(ps.match)
        match_dec = flow.add_node(FlowNode(
            id=f"{psid}__match",
            type="decision",
            label=f"Policy Set Match?\n{match_label}",
        ))
        flow.add_edge(start.id, match_dec.id)
        no_match_end = flow.add_node(FlowNode(
            id=f"{psid}__no_match",
            type="end",
            label="Skip\n(no match)",
        ))
        flow.add_edge(match_dec.id, no_match_end.id, "NO")
        authen_from = match_dec.id
        authen_label: EdgeLabel = "YES"
    else:
        authen_from = start.id
        authen_label = ""

    # ------------------------------------------------------------------
    # Build authz chain first to know its entry node ID
    # ------------------------------------------------------------------
    authz_entry_id = _build_authz_chain(ps, ir, flow, psid)

    # ------------------------------------------------------------------
    # Build authen chain, wiring PASS edges to authz_entry_id
    # ------------------------------------------------------------------
    _build_authen_chain(ps, flow, psid, authen_from, authen_label, authz_entry_id)

    return flow


# ---------------------------------------------------------------------------
# Authz (authorization) chain
# ---------------------------------------------------------------------------

def _build_authz_chain(
    ps: ISEPolicySet,
    ir: ISEPolicyIR,
    flow: FlowIR,
    psid: str,
) -> str:
    """Build the authorization rule chain. Returns the ID of its first node."""
    rules = ps.author_rules

    if not rules:
        deny = flow.add_node(FlowNode(
            id=f"{psid}__authz_no_rules",
            type="end",
            label="Access: DENY\n(no authorization rules)",
        ))
        return deny.id

    first_entry_id: str | None = None
    prev_dec_id: str | None = None

    for i, rule in enumerate(rules):
        if rule.when is not None:
            cond_label = expr_to_node_label(rule.when)
            dec = flow.add_node(FlowNode(
                id=f"{psid}__authz_dec_{i}",
                type="decision",
                label=cond_label,
                trace_rule_id=rule.id,
                rank_group="enf_chain",
            ))
            if first_entry_id is None:
                first_entry_id = dec.id
            if prev_dec_id is not None:
                flow.add_edge(prev_dec_id, dec.id, "NO")

            # YES → action → end
            action_id, _ = _add_authz_action(rule, ir, flow, psid, i)
            flow.add_edge(dec.id, action_id, "YES")
            prev_dec_id = dec.id

        else:
            # Match-all rule: no decision, straight to action
            action_id, _ = _add_authz_action(rule, ir, flow, psid, i)
            if first_entry_id is None:
                first_entry_id = action_id
            if prev_dec_id is not None:
                flow.add_edge(prev_dec_id, action_id, "NO")
            prev_dec_id = None  # chain terminates here (match-all consumes all)

    # Last decision's NO path → implicit deny (only if chain ended with a decision)
    if prev_dec_id is not None:
        implicit_deny = flow.add_node(FlowNode(
            id=f"{psid}__authz_implicit_deny",
            type="end",
            label="Access: DENY\n(implicit)",
        ))
        flow.add_edge(prev_dec_id, implicit_deny.id, "NO")

    return first_entry_id or f"{psid}__authz_no_rules"


def _add_authz_action(
    rule: ISEAuthorRule,
    ir: ISEPolicyIR,
    flow: FlowIR,
    psid: str,
    idx: int,
) -> tuple[str, str]:
    """Add an action node + end node for an authz rule. Returns (action_id, end_id)."""
    profiles = rule.profile_names
    commandsets = rule.commandset_names
    label_parts = profiles + ([f"[{cs}]" for cs in commandsets] if commandsets else [])
    action_label = ", ".join(label_parts) if label_parts else "Apply"
    if rule.security_groups:
        sg_lines = "\n".join(f"Security Group: {sg}" for sg in rule.security_groups)
        action_label = f"{action_label}\n{sg_lines}"
    deny = _is_deny_ise(profiles, ir)

    action = flow.add_node(FlowNode(
        id=f"{psid}__authz_action_{idx}",
        type="action",
        label=action_label,
        trace_rule_id=rule.id,
    ))
    access = "DENY" if deny else "ALLOW"
    end = flow.add_node(FlowNode(
        id=f"{psid}__authz_end_{idx}",
        type="end",
        label=f"Access: {access}",
    ))
    flow.add_edge(action.id, end.id)
    return action.id, end.id


def _is_deny_ise(profile_names: list[str], ir: ISEPolicyIR) -> bool:
    """Return True if any profile in the list is ACCESS_REJECT."""
    for name in profile_names:
        profile = ir.profiles.get(name)
        if profile is not None and profile.access_type == "ACCESS_REJECT":
            return True
        # Fallback name heuristic
        if "deny" in name.lower() or "reject" in name.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Authen (authentication) chain
# ---------------------------------------------------------------------------

def _build_authen_chain(
    ps: ISEPolicySet,
    flow: FlowIR,
    psid: str,
    entry_from: str,
    entry_label: EdgeLabel,
    authz_entry_id: str,
) -> None:
    """Build the authentication rule chain, wiring PASS edges to authz_entry_id."""
    rules = ps.authen_rules

    if not rules:
        no_auth = flow.add_node(FlowNode(
            id=f"{psid}__authen_no_rules",
            type="end",
            label="No authentication rules\nAccess: DENY",
        ))
        flow.add_edge(entry_from, no_auth.id, entry_label)
        return

    # Pre-build all rule nodes to know their entry IDs for lookahead wiring
    rule_meta: list[dict] = []
    for i, rule in enumerate(rules):
        dec_id: str | None = None
        if rule.when is not None:
            dec = flow.add_node(FlowNode(
                id=f"{psid}__authen_dec_{i}",
                type="decision",
                label=expr_to_node_label(rule.when),
                trace_rule_id=rule.id,
                rank_group="authen_chain",
            ))
            dec_id = dec.id

        proc = flow.add_node(FlowNode(
            id=f"{psid}__authen_proc_{i}",
            type="process",
            label=f"Auth: {rule.storename}\n({rule.storetype})",
            trace_rule_id=rule.id,
        ))

        fail = flow.add_node(FlowNode(
            id=f"{psid}__authen_fail_{i}",
            type="end",
            label=f"Auth Failed ({rule.authen_fail_action})",
            sub_label="Access: DENY",
            trace_rule_id=rule.id,
        ))

        rule_meta.append({
            "rule": rule,
            "dec_id": dec_id,
            "proc_id": proc.id,
            "fail_id": fail.id,
            "entry_id": dec_id if dec_id else proc.id,
        })

    # Wire entry edge to first rule
    flow.add_edge(entry_from, rule_meta[0]["entry_id"], entry_label)

    # Wire each rule's internal and inter-rule edges
    for i, rm in enumerate(rule_meta):
        rule: ISEAuthenRule = rm["rule"]
        next_entry_id = rule_meta[i + 1]["entry_id"] if i + 1 < len(rule_meta) else None

        # Decision → PROCESS (YES) or next rule (NO)
        if rm["dec_id"] is not None:
            flow.add_edge(rm["dec_id"], rm["proc_id"], "YES")
            if next_entry_id is not None:
                flow.add_edge(rm["dec_id"], next_entry_id, "NO")
            else:
                no_match = flow.add_node(FlowNode(
                    id=f"{psid}__authen_no_match",
                    type="end",
                    label="No auth rule matched",
                    sub_label="Access: DENY",
                ))
                flow.add_edge(rm["dec_id"], no_match.id, "NO")

        # PROCESS → PASS (authz chain) and FAIL (deny end)
        flow.add_edge(rm["proc_id"], authz_entry_id, "PASS")
        flow.add_edge(rm["proc_id"], rm["fail_id"], "FAIL")

        # PROCESS → CONTINUE (if usernotfoundaction=CONTINUE)
        if rule.user_not_found_action.upper() == "CONTINUE":
            if next_entry_id is not None:
                flow.add_edge(rm["proc_id"], next_entry_id, "CONTINUE", reason="usernotfound")
            else:
                continue_end = flow.add_node(FlowNode(
                    id=f"{psid}__authen_continue_end_{i}",
                    type="end",
                    label="No auth rule matched\n(after CONTINUE)",
                    sub_label="Access: DENY",
                ))
                flow.add_edge(rm["proc_id"], continue_end.id, "CONTINUE", reason="usernotfound")
