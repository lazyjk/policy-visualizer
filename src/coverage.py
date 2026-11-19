"""
Anonymous coverage report for a ClearPass file.

Summarises WHICH features a configuration uses — service templates, profile
types, condition namespaces and operators, settings this version does not
interpret — as counts, so users can share it to help prioritise parser
support without sharing their configuration.

Privacy rules (enforced by tests/test_coverage.py):
- never object names, descriptions, condition values or attribute values
- never auth-source names: "Authorization:Corp-AD" becomes "Authorization:<source>"
- never condition attribute names (they include customer-defined attribute
  aliases); only namespaces and operators
- uninterpreted settings are reported by path shape only, with [name]
  segments removed ("AcctFilterParamList/RulesCondition/@oper")
- warnings are reported as category counts, not text

Entry point: coverage_report(raw, ir) -> dict (deterministic, sorted keys)
"""
from __future__ import annotations

import re
from collections import Counter

from .normalizer import And, BooleanExpr, Not, Op, Or, Predicate
from .policy_ir import PolicyIR

REPORT_VERSION = 1

_BRACKETED = re.compile(r"\[[^\]]*\]")


def _namespace(ns: str) -> str:
    """Drop customer-specific parts of a condition namespace."""
    head, _, rest = ns.partition(":")
    if head in ("Authorization", "Authentication") and rest:
        return f"{head}:<source>"
    return _BRACKETED.sub("<name>", ns)


def _extra_path_shape(path: str) -> str:
    return _BRACKETED.sub("", path)


def _predicates(expr: BooleanExpr | None):
    if expr is None:
        return
    if isinstance(expr, Predicate):
        yield expr
    elif isinstance(expr, (And, Or)):
        for o in expr.operands:
            yield from _predicates(o)
    elif isinstance(expr, Not):
        yield from _predicates(expr.operand)


def _warning_category(msg: str) -> str:
    m = msg.lower()
    if "not found" in m:
        return "unresolved_reference"
    if "unrecognised condition operator" in m:
        return "unknown_operator"
    if "appears more than once" in m:
        return "conflicting_duplicate"
    if "flattened" in m or "no and/or operator" in m or "could not be read" in m:
        return "rule_conversion"
    return "other"


def _sorted(counter: Counter) -> dict[str, int]:
    return {k: counter[k] for k in sorted(counter)}


def coverage_report(raw: dict, ir: PolicyIR) -> dict:
    services = list(ir.services.values())
    svc_types = Counter(s.service_type for s in services)
    svc_templates = Counter(s.template or "(none)" for s in services)
    svc_flags = Counter()
    for s in services:
        for flag in ("monitor_mode", "use_cached_results", "strip_username", "posture_enabled",
                     "profiler_enabled", "audit_enabled", "proxy_accounting"):
            if getattr(s, flag):
                svc_flags[flag] += 1
        if not s.enabled:
            svc_flags["disabled"] += 1
        if s.is_category:
            svc_flags["divider"] += 1
        if s.acct_proxy_targets:
            svc_flags["accounting_proxy"] += 1
        if s.profiler_coa_profile:
            svc_flags["profiler_coa"] += 1
        if s.authorization_source_names:
            svc_flags["authorization_sources"] += 1

    profiles = list(ir.enforcement_profiles.values())
    profile_types = Counter(p.profile_type for p in profiles)
    profile_variants = Counter()
    attr_types = Counter()
    for p in profiles:
        if p.product:
            profile_variants[f"product:{p.product}"] += 1
        if p.profile_type == "radius_coa" and p.template:
            profile_variants[f"coa_template:{p.template}"] += 1
        if p.nad_groups:
            profile_variants["nad_group_restricted"] += 1
        if p.tacacs_services:
            profile_variants["tacacs_services"] += 1
        for a in p.attributes:
            # Attribute types are dictionary namespaces ("Radius:Aruba", "DUR:durPluginA",
            # "cpass:HTTP"); names and values are not reported.
            attr_types[_namespace(a.type) or "(none)"] += 1

    operators = Counter()
    unknown_operators = Counter()
    namespaces = Counter()
    rule_counts = []
    algos = Counter()
    exprs: list[BooleanExpr | None] = [s.match for s in services]
    for pol, kind in [(p, "role_mapping") for p in ir.role_mapping_policies.values()] + \
                     [(p, "enforcement") for p in ir.enforcement_policies.values()]:
        algos[f"{kind}:{pol.rule_combine_algo}"] += 1
        rule_counts.append(len(pol.rules))
        exprs.extend(r.when for r in pol.rules)
    for expr in exprs:
        for pred in _predicates(expr):
            raw_op = pred.raw_operator or pred.op.value
            operators[raw_op] += 1
            if pred.op is Op.unknown:
                unknown_operators[raw_op] += 1
            namespaces[_namespace(pred.namespace) or "(none)"] += 1

    extras = Counter()
    for s in services:
        for e in s.extras:
            extras[f"service:{_extra_path_shape(e.path)}"] += 1
    for p in profiles:
        for e in p.extras:
            owner = p.element_type or p.profile_type
            extras[f"{owner}:{_extra_path_shape(e.path)}"] += 1

    return {
        "report_version": REPORT_VERSION,
        "source": {
            "format": ir.source_format,
            "clearpass_version": raw.get("clearpassVersion") or None,
        },
        "services": {
            "total": len(services),
            "by_type": _sorted(svc_types),
            "by_template": _sorted(svc_templates),
            "options": _sorted(svc_flags),
        },
        "policies": {
            "role_mapping": len(ir.role_mapping_policies),
            "enforcement": len(ir.enforcement_policies),
            "by_algorithm": _sorted(algos),
            "rules_total": sum(rule_counts),
            "rules_max_per_policy": max(rule_counts, default=0),
        },
        "profiles": {
            "total": len(profiles),
            "by_type": _sorted(profile_types),
            "variants": _sorted(profile_variants),
            "attribute_namespaces": _sorted(attr_types),
        },
        "conditions": {
            "operators": _sorted(operators),
            "unknown_operators": _sorted(unknown_operators),
            "namespaces": _sorted(namespaces),
        },
        "authentication": {
            "method_types": _sorted(Counter(m.method_type or "(none)" for m in ir.auth_methods.values())),
            "source_types": _sorted(Counter(s.source_type or "(none)" for s in ir.auth_sources.values())),
        },
        "roles": len(ir.roles),
        "uninterpreted_settings": _sorted(extras),
        "warnings": _sorted(Counter(_warning_category(w) for w in ir.warnings)),
    }
