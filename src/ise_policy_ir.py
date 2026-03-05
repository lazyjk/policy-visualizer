"""
ISE Policy IR

Converts the raw ISE object model (from ise_parser) into a structured
ISEPolicyIR with typed dataclasses. DISABLED rules are filtered out;
DISABLED policy sets are retained so the picker can list them.

Entry point: ise_build(raw, source_file) -> ISEPolicyIR
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ise_normalizer import normalize_ise_condition
from .normalizer import BooleanExpr


@dataclass
class ISEAuthenRule:
    id: str
    name: str
    index: int
    when: BooleanExpr | None      # None = match-all
    storetype: str
    storename: str
    authen_fail_action: str       # "REJECT" | "DROP"
    user_not_found_action: str    # "REJECT" | "CONTINUE" | "DROP"


@dataclass
class ISEAuthorRule:
    id: str
    name: str
    index: int
    when: BooleanExpr | None
    profile_names: list[str]
    commandset_names: list[str]   # TACACS only; empty for RADIUS
    security_groups: list[str] = field(default_factory=list)  # SGT group names; empty if not set


@dataclass
class ISEProfile:
    name: str
    profile_type: str             # "standard" | "tacacs" | "commandset"
    access_type: str | None       # "ACCESS_ACCEPT" | "ACCESS_REJECT" | None


@dataclass
class ISEPolicySet:
    id: str
    name: str
    description: str
    rank: int
    set_type: str                 # "RADIUS" | "TACACS"
    allowed_protocols: str
    match: BooleanExpr | None     # None = match-all
    authen_rules: list[ISEAuthenRule]   # ENABLED only, sorted by rank
    author_rules: list[ISEAuthorRule]   # ENABLED only, sorted by rank


@dataclass
class ISEPolicyIR:
    version: str = "1.0"
    source_file: str = ""
    policy_sets: list[ISEPolicySet] = field(default_factory=list)
    profiles: dict[str, ISEProfile] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def ise_build(raw: dict, source_file: str = "") -> ISEPolicyIR:
    """Build an ISEPolicyIR from the raw ISE object model."""
    ir = ISEPolicyIR(source_file=source_file)
    library: dict[str, dict] = raw.get("library_conditions", {})

    # Build profile dict
    for name, p in raw.get("profiles", {}).items():
        ir.profiles[name] = ISEProfile(
            name=p["name"],
            profile_type=p.get("profile_type", "standard"),
            access_type=p.get("access_type"),
        )

    # Build policy sets
    for ps_raw in raw.get("policy_sets", []):
        ps = _build_policy_set(ps_raw, library, ir)
        ir.policy_sets.append(ps)

    return ir


def _build_policy_set(ps_raw: dict, library: dict, ir: ISEPolicyIR) -> ISEPolicySet:
    match = normalize_ise_condition(
        ps_raw.get("match_condition"),
        library,
        ir.warnings,
    )

    authen_rules = []
    for r in sorted(
        (r for r in ps_raw.get("authen_rules", []) if r.get("status") == "ENABLED"),
        key=lambda r: r["rank"],
    ):
        authen_rules.append(_build_authen_rule(r, library, ir))

    author_rules = []
    for r in sorted(
        (r for r in ps_raw.get("author_rules", []) if r.get("status") == "ENABLED"),
        key=lambda r: r["rank"],
    ):
        author_rules.append(_build_author_rule(r, library, ir))

    return ISEPolicySet(
        id=ps_raw["id"],
        name=ps_raw["name"],
        description=ps_raw.get("description", ""),
        rank=ps_raw.get("rank", 0),
        set_type=ps_raw.get("set_type", "RADIUS"),
        allowed_protocols=ps_raw.get("allowed_protocols", ""),
        match=match,
        authen_rules=authen_rules,
        author_rules=author_rules,
    )


def _build_authen_rule(r: dict, library: dict, ir: ISEPolicyIR) -> ISEAuthenRule:
    return ISEAuthenRule(
        id=r["id"],
        name=r["name"],
        index=r["rank"],
        when=normalize_ise_condition(r.get("condition"), library, ir.warnings),
        storetype=r.get("storetype", ""),
        storename=r.get("storename", ""),
        authen_fail_action=r.get("authen_fail_action", "REJECT"),
        user_not_found_action=r.get("user_not_found_action", "REJECT"),
    )


def _build_author_rule(r: dict, library: dict, ir: ISEPolicyIR) -> ISEAuthorRule:
    profile_names = r.get("profiles", [])
    for pname in profile_names:
        if pname not in ir.profiles:
            ir.warnings.append(f"Unknown profile {pname!r} in author rule {r['name']!r}")
            ir.profiles[pname] = ISEProfile(
                name=pname,
                profile_type="standard",
                access_type=None,
            )
    commandset_names = r.get("commandsets", [])
    for csname in commandset_names:
        if csname not in ir.profiles:
            ir.warnings.append(f"Unknown commandset {csname!r} in author rule {r['name']!r}")
            ir.profiles[csname] = ISEProfile(
                name=csname,
                profile_type="commandset",
                access_type=None,
            )
    return ISEAuthorRule(
        id=r["id"],
        name=r["name"],
        index=r["rank"],
        when=normalize_ise_condition(r.get("condition"), library, ir.warnings),
        profile_names=profile_names,
        commandset_names=commandset_names,
        security_groups=r.get("groups", []),
    )
