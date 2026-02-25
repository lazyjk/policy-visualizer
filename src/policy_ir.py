"""
Phase 3: Policy IR Construction

Produces a fully normalized Policy IR from the raw object model (parser output).
Uses stable deterministic IDs derived from object names.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .normalizer import BooleanExpr, normalize


def _stable_id(name: str) -> str:
    """Generate a stable slug-style ID from an object name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    suffix = hashlib.sha256(name.encode()).hexdigest()[:6]
    return f"{slug}_{suffix}" if slug else f"id_{suffix}"


# ---------------------------------------------------------------------------
# IR dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AuthMethod:
    id: str
    name: str
    method_type: str
    params: dict[str, str] = field(default_factory=dict)
    inner_methods: list[str] = field(default_factory=list)


@dataclass
class AuthSource:
    id: str
    name: str
    source_type: str
    description: str = ""
    is_authz_source: bool = False


@dataclass
class Role:
    id: str
    name: str
    description: str = ""


@dataclass
class RuleThen:
    pass


@dataclass
class SetRole(RuleThen):
    role_id: str
    role_name: str


@dataclass
class ApplyProfiles(RuleThen):
    profile_ids: list[str] = field(default_factory=list)
    profile_names: list[str] = field(default_factory=list)


@dataclass
class RuleFlow:
    on_match: str = "stop"  # "stop" | "continue"


@dataclass
class PolicyRule:
    id: str
    index: int
    when: BooleanExpr | None
    then: RuleThen
    flow: RuleFlow = field(default_factory=RuleFlow)


@dataclass
class RoleMappingPolicy:
    id: str
    name: str
    rule_combine_algo: str
    rules: list[PolicyRule] = field(default_factory=list)
    default: SetRole | None = None


@dataclass
class ServiceAuthentication:
    method_ids: list[str] = field(default_factory=list)
    method_names: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    source_names: list[str] = field(default_factory=list)


@dataclass
class EnforcementPolicy:
    id: str
    name: str
    policy_type: str
    rules: list[PolicyRule] = field(default_factory=list)
    default: ApplyProfiles | None = None


@dataclass
class EnforcementProfile:
    id: str
    name: str
    profile_type: str  # "radius_accept" | "radius_reject" | "post_auth"
    action: str = ""
    description: str = ""


@dataclass
class Service:
    id: str
    name: str
    description: str
    service_type: str
    match: BooleanExpr | None
    authentication: ServiceAuthentication
    role_mapping_policy_id: str
    role_mapping_policy_name: str
    enforcement_policy_id: str
    enforcement_policy_name: str


@dataclass
class PolicyIR:
    version: str
    source_file: str
    services: dict[str, Service] = field(default_factory=dict)
    role_mapping_policies: dict[str, RoleMappingPolicy] = field(default_factory=dict)
    enforcement_policies: dict[str, EnforcementPolicy] = field(default_factory=dict)
    enforcement_profiles: dict[str, EnforcementProfile] = field(default_factory=dict)
    roles: dict[str, Role] = field(default_factory=dict)
    auth_methods: dict[str, AuthMethod] = field(default_factory=dict)
    auth_sources: dict[str, AuthSource] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build(raw: dict[str, Any], source_file: str = "") -> PolicyIR:
    ir = PolicyIR(version="1.0", source_file=source_file)
    unresolved: list[str] = []

    # Roles
    for r in raw.get("roles", []):
        rid = _stable_id(r["name"])
        ir.roles[rid] = Role(id=rid, name=r["name"], description=r.get("description", ""))
    role_by_name = {v.name: v for v in ir.roles.values()}

    # Auth methods
    for am in raw.get("authMethods", []):
        mid = _stable_id(am["name"])
        ir.auth_methods[mid] = AuthMethod(
            id=mid,
            name=am["name"],
            method_type=am.get("methodType", ""),
            params=am.get("params", {}),
            inner_methods=am.get("innerMethods", []),
        )
    method_by_name = {v.name: v for v in ir.auth_methods.values()}

    # Auth sources
    for src in raw.get("authSources", []):
        sid = _stable_id(src["name"])
        ir.auth_sources[sid] = AuthSource(
            id=sid,
            name=src["name"],
            source_type=src.get("type", ""),
            description=src.get("description", ""),
            is_authz_source=src.get("isAuthorizationSource", "false").lower() == "true",
        )
    source_by_name = {v.name: v for v in ir.auth_sources.values()}

    # Enforcement profiles (RADIUS + PostAuth)
    for rp in raw.get("radiusEnfProfiles", []):
        pid = _stable_id(rp["name"])
        action = rp.get("action", "").lower()
        profile_type = "radius_accept" if action == "accept" else "radius_reject"
        ir.enforcement_profiles[pid] = EnforcementProfile(
            id=pid, name=rp["name"],
            profile_type=profile_type,
            action=action,
            description=rp.get("description", ""),
        )
    for pp in raw.get("postAuthEnfProfiles", []):
        pid = _stable_id(pp["name"])
        ir.enforcement_profiles[pid] = EnforcementProfile(
            id=pid, name=pp["name"],
            profile_type="post_auth",
            description=pp.get("description", ""),
        )
    for tp in raw.get("tacacsEnfProfiles", []):
        pid = _stable_id(tp["name"])
        action = tp.get("action", "").lower()
        ir.enforcement_profiles[pid] = EnforcementProfile(
            id=pid, name=tp["name"],
            profile_type="tacacs_accept" if action == "accept" else "tacacs_other",
            action=action,
            description=tp.get("description", ""),
        )
    profile_by_name = {v.name: v for v in ir.enforcement_profiles.values()}

    def _resolve_profiles(display_value: str, context: str = "") -> tuple[list[str], list[str]]:
        """Parse a comma-separated displayValue of profile names."""
        names = [n.strip() for n in display_value.split(",") if n.strip()]
        ids = []
        for n in names:
            if n in profile_by_name:
                ids.append(profile_by_name[n].id)
            else:
                ctx = f" ({context})" if context else ""
                unresolved.append(f"EnforcementProfile '{n}' not found{ctx}")
                ids.append(_stable_id(n))  # placeholder; ValueError raised at end
        return ids, names

    # Role mapping policies
    for rm in raw.get("roleMappings", []):
        rmid = _stable_id(rm["name"])
        rules = []
        for raw_rule in rm.get("rules", []):
            expr = normalize(raw_rule.get("expression"))
            results = raw_rule.get("results", [])
            then: RuleThen
            role_result = next((r for r in results if r.get("name") == "Role"), None)
            if role_result:
                role_name = role_result.get("displayValue", "")
                role = role_by_name.get(role_name)
                if role is None and role_name:
                    unresolved.append(
                        f"Role '{role_name}' not found (rule in RoleMappingPolicy '{rm['name']}')"
                    )
                then = SetRole(
                    role_id=role.id if role else _stable_id(role_name),
                    role_name=role_name,
                )
            else:
                then = SetRole(role_id="unknown", role_name="Unknown")
            rule_id = f"{rmid}_rule_{raw_rule['index']}"
            rules.append(PolicyRule(id=rule_id, index=raw_rule["index"], when=expr, then=then))

        default_role_name = rm.get("defaultRole", "")
        default_role = role_by_name.get(default_role_name)
        if default_role_name and default_role is None:
            unresolved.append(
                f"Role '{default_role_name}' not found (default in RoleMappingPolicy '{rm['name']}')"
            )
        default = SetRole(
            role_id=default_role.id if default_role else _stable_id(default_role_name),
            role_name=default_role_name,
        ) if default_role_name else None

        ir.role_mapping_policies[rmid] = RoleMappingPolicy(
            id=rmid,
            name=rm["name"],
            rule_combine_algo=rm.get("ruleCombineAlgo", "first-applicable"),
            rules=rules,
            default=default,
        )
    rm_by_name = {v.name: v for v in ir.role_mapping_policies.values()}

    # Enforcement policies
    for ep in raw.get("enforcementPolicies", []):
        epid = _stable_id(ep["name"])
        rules = []
        for raw_rule in ep.get("rules", []):
            expr = normalize(raw_rule.get("expression"))
            results = raw_rule.get("results", [])
            enf_result = next((r for r in results if r.get("name") == "Enforcement-Profile"), None)
            profile_ids: list[str] = []
            profile_names: list[str] = []
            if enf_result:
                ctx = f"rule in EnforcementPolicy '{ep['name']}'"
                profile_ids, profile_names = _resolve_profiles(enf_result.get("displayValue", ""), ctx)
            then = ApplyProfiles(profile_ids=profile_ids, profile_names=profile_names)
            rule_id = f"{epid}_rule_{raw_rule['index']}"
            rules.append(PolicyRule(id=rule_id, index=raw_rule["index"], when=expr, then=then))

        default_profile_name = ep.get("defaultProfile", "")
        default_profile = profile_by_name.get(default_profile_name)
        if default_profile_name and default_profile is None:
            unresolved.append(
                f"EnforcementProfile '{default_profile_name}' not found (default in EnforcementPolicy '{ep['name']}')"
            )
        default = ApplyProfiles(
            profile_ids=[default_profile.id] if default_profile else [_stable_id(default_profile_name)],
            profile_names=[default_profile_name] if default_profile_name else [],
        ) if default_profile_name else None

        ir.enforcement_policies[epid] = EnforcementPolicy(
            id=epid,
            name=ep["name"],
            policy_type=ep.get("policyType", ""),
            rules=rules,
            default=default,
        )
    ep_by_name = {v.name: v for v in ir.enforcement_policies.values()}

    # Services
    for svc in raw.get("services", []):
        svid = _stable_id(svc["name"])
        match_expr = normalize(svc.get("matchExpression"))

        method_ids = []
        method_names = svc.get("authMethods", [])
        for mn in method_names:
            m = method_by_name.get(mn)
            if m is None and mn:
                unresolved.append(f"AuthMethod '{mn}' not found (referenced in Service '{svc['name']}')")
            method_ids.append(m.id if m else _stable_id(mn))

        source_ids = []
        source_names = svc.get("authSources", [])
        for sn in source_names:
            s = source_by_name.get(sn)
            if s is None and sn:
                unresolved.append(f"AuthSource '{sn}' not found (referenced in Service '{svc['name']}')")
            source_ids.append(s.id if s else _stable_id(sn))

        rm_names = svc.get("roleMappings", [])
        rm_name = rm_names[0] if rm_names else ""
        rm = rm_by_name.get(rm_name)
        if rm_name and rm is None:
            unresolved.append(f"RoleMappingPolicy '{rm_name}' not found (referenced in Service '{svc['name']}')")
        rm_id = rm.id if rm else _stable_id(rm_name)

        ep_names = svc.get("enfPolicies", [])
        ep_name = ep_names[0] if ep_names else ""
        ep = ep_by_name.get(ep_name)
        if ep_name and ep is None:
            unresolved.append(f"EnforcementPolicy '{ep_name}' not found (referenced in Service '{svc['name']}')")
        ep_id = ep.id if ep else _stable_id(ep_name)

        ir.services[svid] = Service(
            id=svid,
            name=svc["name"],
            description=svc.get("description", ""),
            service_type=svc.get("serviceType", "RADIUS"),
            match=match_expr,
            authentication=ServiceAuthentication(
                method_ids=method_ids,
                method_names=method_names,
                source_ids=source_ids,
                source_names=source_names,
            ),
            role_mapping_policy_id=rm_id,
            role_mapping_policy_name=rm_name,
            enforcement_policy_id=ep_id,
            enforcement_policy_name=ep_name,
        )

    if unresolved:
        raise ValueError("Unresolved references:\n" + "\n".join(unresolved))

    return ir
