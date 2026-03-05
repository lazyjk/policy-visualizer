"""
ISE Condition Normalizer

Converts ISE raw condition dicts (from ise_parser) into canonical BooleanExpr AST
using the same Predicate/And/Or/Not/Op types as the ClearPass normalizer.

Key differences from ClearPass normalizer:
- ISE conditions are a nested tree (AND_BLOCK/OR_BLOCK/SINGLE/REFERENCE),
  not a flat AttributeList.
- ISE operators are camelCase (e.g. "endsWith"), not SCREAMING_SNAKE_CASE.
  Do NOT use Op.from_raw() here.
- REFERENCE nodes must be resolved against the library_conditions dict.
- isNot=true at any node wraps the result in Not().

Entry point: normalize_ise_condition(cond, library, warnings) -> BooleanExpr | None
"""
from __future__ import annotations

from .normalizer import And, BooleanExpr, Not, Op, Or, Predicate

# ---------------------------------------------------------------------------
# ISE operator mapping (camelCase → Op enum)
# ---------------------------------------------------------------------------

_ISE_OP_MAP: dict[str, Op] = {
    # camelCase (documented ISE operator names)
    "contains": Op.contains,
    "endsWith": Op.ends_with,
    "equals": Op.equals,
    "greaterOrEquals": Op.greater_than_or_equals,
    "greaterThan": Op.greater_than,
    "in": Op.in_,
    "ipEquals": Op.ip_equals,
    "ipGreaterThan": Op.ip_greater_than,
    "ipLessThan": Op.ip_less_than,
    "ipNotEquals": Op.ip_not_equals,
    "lessOrEquals": Op.less_than_or_equals,
    "lessThan": Op.less_than,
    "matches": Op.regex,          # ISE "matches" = regex
    "notContains": Op.not_contains,
    "notEndsWith": Op.not_ends_with,
    "notEquals": Op.not_equals,
    "notIn": Op.not_in,
    "notStartsWith": Op.not_starts_with,
    "startsWith": Op.starts_with,
    # SCREAMING_SNAKE_CASE aliases (used in some ISE XML exports)
    "CONTAINS": Op.contains,
    "ENDS_WITH": Op.ends_with,
    "EQUALS": Op.equals,
    "GREATER_OR_EQUALS": Op.greater_than_or_equals,
    "GREATER_THAN": Op.greater_than,
    "IN": Op.in_,
    "LESS_OR_EQUALS": Op.less_than_or_equals,
    "LESS_THAN": Op.less_than,
    "MATCHES": Op.regex,
    "NOT_CONTAINS": Op.not_contains,
    "NOT_ENDS_WITH": Op.not_ends_with,
    "NOT_EQUALS": Op.not_equals,
    "NOT_IN": Op.not_in,
    "NOT_STARTS_WITH": Op.not_starts_with,
    "STARTS_WITH": Op.starts_with,
}


def _ise_op(raw: str) -> Op:
    try:
        return _ISE_OP_MAP[raw]
    except KeyError:
        raise ValueError(f"Unknown ISE operator: {raw!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def normalize_ise_condition(
    cond: dict | None,
    library: dict[str, dict],
    warnings: list[str],
) -> BooleanExpr | None:
    """
    Convert a raw ISE condition dict into a canonical BooleanExpr.

    Returns None for match-all (empty condition).
    Appends to warnings for unresolved REFERENCE nodes.
    """
    if cond is None:
        return None
    return _normalize_node(cond, library, warnings)


# ---------------------------------------------------------------------------
# Internal recursive descent
# ---------------------------------------------------------------------------

def _normalize_node(
    node: dict,
    library: dict[str, dict],
    warnings: list[str],
) -> BooleanExpr | None:
    node_type = node.get("type", "")
    is_not: bool = node.get("is_not", False)

    if node_type == "SINGLE":
        result = _normalize_single(node)

    elif node_type == "REFERENCE":
        result = _normalize_reference(node, library, warnings)

    elif node_type in ("AND_BLOCK", "OR_BLOCK"):
        result = _normalize_block(node, library, warnings)

    else:
        return None

    if result is None:
        return None
    if is_not:
        return Not(operand=result)
    return result


def _normalize_single(node: dict) -> BooleanExpr | None:
    operator_raw = node.get("operator", "")
    if not operator_raw:
        return None
    return Predicate(
        namespace=node.get("lhs_dictionary", ""),
        attribute=node.get("lhs_attribute", ""),
        op=_ise_op(operator_raw),
        rhs_raw=node.get("rhs_attribute", ""),
        rhs_display=node.get("rhs_attribute", ""),
        raw_operator=operator_raw,
    )


def _normalize_reference(
    node: dict,
    library: dict[str, dict],
    warnings: list[str],
) -> BooleanExpr | None:
    ref_id = node.get("ref_id", "")
    lib_entry = library.get(ref_id)
    if lib_entry is None:
        warnings.append(f"Unresolved library condition reference: {ref_id!r}")
        return And(operands=[])
    lib_cond = lib_entry.get("condition")
    if lib_cond is None:
        return None
    # Recurse into the resolved condition; is_not on the REFERENCE node is
    # handled by the caller wrapping in Not()
    return _normalize_node(lib_cond, library, warnings)


def _normalize_block(
    node: dict,
    library: dict[str, dict],
    warnings: list[str],
) -> BooleanExpr | None:
    node_type = node.get("type", "AND_BLOCK")
    children_raw = node.get("children", [])
    operands: list[BooleanExpr] = []
    for child in children_raw:
        result = _normalize_node(child, library, warnings)
        if result is not None:
            operands.append(result)

    if not operands:
        return And(operands=[])

    # Single-predicate unwrap: skip the boolean wrapper
    if len(operands) == 1:
        return operands[0]

    if node_type == "OR_BLOCK":
        return Or(operands=operands)
    return And(operands=operands)
