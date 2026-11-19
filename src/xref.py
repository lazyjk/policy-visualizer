"""
Where-used / unused-object analysis over a ClearPass PolicyIR.

For every policy object (role-mapping and enforcement policies, enforcement
profiles, roles, authentication methods and sources) this lists which
services, policies and rules reference it, and classifies it:

  used           reachable from at least one enabled service
  only_disabled  reachable only from disabled services
  unused         not reachable from any service

Reachability follows the evaluation path service -> policies -> rules ->
profiles/roles, so a profile referenced only by an unused policy is unused.

Input matters: an XML export only contains objects reachable from the
exported services, so "unused" findings are only complete for a ClearPass DB
backup (.pgdump), which holds every configured object. The result says which
input it came from so the UI can explain this.

Entry point: build_xref(ir) -> dict (deterministic ordering)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .normalizer import And, BooleanExpr, Not, Or, Predicate
from .policy_ir import ApplyProfiles, PolicyIR, SetRole

# Display order of object kinds.
KINDS = (
    "role_mapping_policy", "enforcement_policy", "enforcement_profile",
    "role", "auth_method", "auth_source",
)
_KIND_RANK = {k: i for i, k in enumerate(KINDS)}


@dataclass
class _Obj:
    kind: str
    id: str
    name: str
    used_by: list[dict] = field(default_factory=list)
    reached_enabled: bool = False
    reached_disabled: bool = False
    assigned: bool = False   # roles: set by a role-mapping rule/default
    tested: bool = False     # roles: appear in a Tips:Role condition


def is_builtin(name: str) -> bool:
    """ClearPass system objects are named in square brackets, e.g. "[Allow Access Profile]"."""
    return name.startswith("[") and name.endswith("]")


def _role_names_in(expr: BooleanExpr | None) -> list[str]:
    """Role names tested by Tips:Role predicates (values are '|'-separated)."""
    out: list[str] = []

    def walk(e: BooleanExpr | None) -> None:
        if e is None:
            return
        if isinstance(e, Predicate):
            if e.namespace == "Tips" and e.attribute == "Role":
                out.extend(v.strip() for v in e.rhs_raw.split("|") if v.strip())
        elif isinstance(e, (And, Or)):
            for o in e.operands:
                walk(o)
        elif isinstance(e, Not):
            walk(e.operand)

    walk(expr)
    return out


def build_xref(ir: PolicyIR) -> dict:
    objs: dict[tuple[str, str], _Obj] = {}

    def obj(kind: str, oid: str, name: str) -> _Obj:
        key = (kind, oid)
        if key not in objs:
            objs[key] = _Obj(kind=kind, id=oid, name=name)
        return objs[key]

    for p in ir.role_mapping_policies.values():
        obj("role_mapping_policy", p.id, p.name)
    for p in ir.enforcement_policies.values():
        obj("enforcement_policy", p.id, p.name)
    for p in ir.enforcement_profiles.values():
        obj("enforcement_profile", p.id, p.name)
    for r in ir.roles.values():
        obj("role", r.id, r.name)
    for m in ir.auth_methods.values():
        obj("auth_method", m.id, m.name)
    for s in ir.auth_sources.values():
        obj("auth_source", s.id, s.name)

    role_by_name = {r.name: r for r in ir.roles.values()}
    source_by_name = {s.name: s for s in ir.auth_sources.values()}
    profile_by_name = {p.name: p for p in ir.enforcement_profiles.values()}

    def ref(kind: str, oid: str, by_kind: str, by_id: str, by_name: str, where: str) -> None:
        o = objs.get((kind, oid))
        if o is not None:
            o.used_by.append({"kind": by_kind, "id": by_id, "name": by_name, "where": where})

    # --- direct references ------------------------------------------------------
    # Edges used afterwards for reachability: (from kind, id) -> [(to kind, id)]
    edges: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

    for svc in ir.services.values():
        src = ("service", svc.id)
        for mid in svc.authentication.method_ids:
            ref("auth_method", mid, "service", svc.id, svc.name, "authentication method")
            edges[src].append(("auth_method", mid))
        for sid in svc.authentication.source_ids:
            ref("auth_source", sid, "service", svc.id, svc.name, "authentication source")
            edges[src].append(("auth_source", sid))
        for name in svc.authorization_source_names:
            s = source_by_name.get(name)
            if s is not None:
                ref("auth_source", s.id, "service", svc.id, svc.name, "authorization source")
                edges[src].append(("auth_source", s.id))
        if svc.role_mapping_policy_name and ("role_mapping_policy", svc.role_mapping_policy_id) in objs:
            ref("role_mapping_policy", svc.role_mapping_policy_id, "service", svc.id, svc.name, "role mapping")
            edges[src].append(("role_mapping_policy", svc.role_mapping_policy_id))
        if svc.enforcement_policy_name and ("enforcement_policy", svc.enforcement_policy_id) in objs:
            ref("enforcement_policy", svc.enforcement_policy_id, "service", svc.id, svc.name, "enforcement")
            edges[src].append(("enforcement_policy", svc.enforcement_policy_id))
        if svc.profiler_coa_profile:
            p = profile_by_name.get(svc.profiler_coa_profile)
            if p is not None:
                ref("enforcement_profile", p.id, "service", svc.id, svc.name, "profiler CoA")
                edges[src].append(("enforcement_profile", p.id))

    method_by_name = {m.name: m for m in ir.auth_methods.values()}
    for m in ir.auth_methods.values():
        for inner_name in m.inner_methods:
            inner = method_by_name.get(inner_name)
            if inner is not None:
                ref("auth_method", inner.id, "auth_method", m.id, m.name, "inner method")
                edges[("auth_method", m.id)].append(("auth_method", inner.id))

    def condition_roles(policy_kind: str, policy_id: str, policy_name: str, rule_pos: int, expr) -> None:
        for role_name in _role_names_in(expr):
            role = role_by_name.get(role_name)
            if role is None:
                continue
            objs[("role", role.id)].tested = True
            ref("role", role.id, policy_kind, policy_id, policy_name, f"condition in rule {rule_pos}")
            edges[(policy_kind, policy_id)].append(("role", role.id))

    for p in ir.role_mapping_policies.values():
        key = ("role_mapping_policy", p.id)
        for pos, rule in enumerate(sorted(p.rules, key=lambda r: r.index), start=1):
            condition_roles(*key, p.name, pos, rule.when)
            if isinstance(rule.then, SetRole) and ("role", rule.then.role_id) in objs:
                objs[("role", rule.then.role_id)].assigned = True
                ref("role", rule.then.role_id, *key, p.name, f"set by rule {pos}")
                edges[key].append(("role", rule.then.role_id))
        if isinstance(p.default, SetRole) and ("role", p.default.role_id) in objs:
            objs[("role", p.default.role_id)].assigned = True
            ref("role", p.default.role_id, *key, p.name, "default role")
            edges[key].append(("role", p.default.role_id))

    for p in ir.enforcement_policies.values():
        key = ("enforcement_policy", p.id)
        for pos, rule in enumerate(sorted(p.rules, key=lambda r: r.index), start=1):
            condition_roles(*key, p.name, pos, rule.when)
            if isinstance(rule.then, ApplyProfiles):
                for pid in rule.then.profile_ids:
                    ref("enforcement_profile", pid, *key, p.name, f"rule {pos}")
                    edges[key].append(("enforcement_profile", pid))
        if isinstance(p.default, ApplyProfiles):
            for pid in p.default.profile_ids:
                ref("enforcement_profile", pid, *key, p.name, "default profile")
                edges[key].append(("enforcement_profile", pid))

    # --- reachability from services -------------------------------------------
    def reach(start: tuple[str, str], flag: str) -> None:
        stack, seen = [start], {start}
        while stack:
            for nxt in edges.get(stack.pop(), []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                o = objs.get(nxt)
                if o is not None:
                    setattr(o, flag, True)
                stack.append(nxt)

    for svc in ir.services.values():
        reach(("service", svc.id), "reached_enabled" if svc.enabled else "reached_disabled")

    # --- output -----------------------------------------------------------------
    def status(o: _Obj) -> str:
        if o.reached_enabled:
            return "used"
        return "only_disabled" if o.reached_disabled else "unused"

    ordered = sorted(objs.values(), key=lambda o: (_KIND_RANK[o.kind], o.name.lower(), o.id))
    objects = [
        {
            "kind": o.kind,
            "id": o.id,
            "name": o.name,
            "builtin": is_builtin(o.name),
            "status": status(o),
            "used_by": sorted(o.used_by, key=lambda u: (u["kind"], u["name"].lower(), u["where"])),
        }
        for o in ordered
    ]

    findings: list[dict] = []
    for o in ordered:
        st = status(o)
        if st != "used":
            findings.append({
                "code": st,
                "kind": o.kind, "id": o.id, "name": o.name, "builtin": is_builtin(o.name),
                "message": (
                    "Not used by any service" if st == "unused"
                    else "Used only by disabled services"
                ),
            })
        if o.kind == "role" and o.assigned and not o.tested:
            findings.append({
                "code": "role_assigned_never_tested",
                "kind": o.kind, "id": o.id, "name": o.name, "builtin": is_builtin(o.name),
                "message": "Assigned by role mapping but never checked in a condition",
            })
        if o.kind == "role" and o.tested and not o.assigned:
            findings.append({
                "code": "role_tested_never_assigned",
                "kind": o.kind, "id": o.id, "name": o.name, "builtin": is_builtin(o.name),
                "message": (
                    "Checked in a condition but not set by any role-mapping policy "
                    "(it may still come from an authentication source or local user)"
                ),
            })

    return {
        "source_format": ir.source_format,
        "complete": ir.source_format == "pgdump",
        "objects": objects,
        "findings": findings,
    }
