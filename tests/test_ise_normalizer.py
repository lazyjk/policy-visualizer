"""Tests for ISE Condition Normalizer (src/ise_normalizer.py)."""
import pytest

from src.ise_normalizer import normalize_ise_condition, _ise_op
from src.normalizer import And, Not, Op, Or, Predicate


# ---------------------------------------------------------------------------
# Helpers — raw condition dict constructors
# ---------------------------------------------------------------------------

def _single(attr, dictionary, op, rhs, is_not=False):
    return {
        "type": "SINGLE",
        "is_not": is_not,
        "lhs_attribute": attr,
        "lhs_dictionary": dictionary,
        "rhs_attribute": rhs,
        "operator": op,
    }


def _and(*children, is_not=False):
    return {"type": "AND_BLOCK", "is_not": is_not, "children": list(children)}


def _or(*children, is_not=False):
    return {"type": "OR_BLOCK", "is_not": is_not, "children": list(children)}


def _ref(ref_id, is_not=False):
    return {"type": "REFERENCE", "ref_id": ref_id, "is_not": is_not}


# ---------------------------------------------------------------------------
# None (match-all)
# ---------------------------------------------------------------------------

def test_none_returns_none():
    assert normalize_ise_condition(None, {}, []) is None


# ---------------------------------------------------------------------------
# SINGLE nodes
# ---------------------------------------------------------------------------

def test_single_equals():
    cond = _single("Protocol", "Radius", "equals", "Dot1X")
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)
    assert result.op == Op.equals
    assert result.attribute == "Protocol"
    assert result.namespace == "Radius"
    assert result.rhs_raw == "Dot1X"


def test_single_is_not_wraps_in_not():
    cond = _single("Protocol", "Radius", "equals", "Dot1X", is_not=True)
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Not)
    assert isinstance(result.operand, Predicate)


def test_single_no_operator_returns_none():
    cond = {"type": "SINGLE", "is_not": False, "lhs_attribute": "A", "lhs_dictionary": "D", "rhs_attribute": "v", "operator": ""}
    assert normalize_ise_condition(cond, {}, []) is None


# ---------------------------------------------------------------------------
# AND_BLOCK / OR_BLOCK
# ---------------------------------------------------------------------------

def test_and_block_two_children():
    cond = _and(
        _single("Protocol", "Radius", "equals", "Dot1X"),
        _single("Called-Station-ID", "Radius", "startsWith", "00-11"),
    )
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, And)
    assert len(result.operands) == 2


def test_or_block_two_children():
    cond = _or(
        _single("Protocol", "Radius", "equals", "Dot1X"),
        _single("Protocol", "Radius", "equals", "MAB"),
    )
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Or)
    assert len(result.operands) == 2


def test_single_predicate_unwrap_and():
    """AND_BLOCK with one child is unwrapped to the child directly."""
    cond = _and(_single("Protocol", "Radius", "equals", "Dot1X"))
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)


def test_single_predicate_unwrap_or():
    """OR_BLOCK with one child is unwrapped to the child directly."""
    cond = _or(_single("Protocol", "Radius", "equals", "Dot1X"))
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)


def test_empty_and_block_returns_degenerate():
    cond = _and()
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, And)
    assert result.operands == []


def test_and_block_is_not_wraps_in_not():
    cond = _and(
        _single("Protocol", "Radius", "equals", "Dot1X"),
        _single("Protocol", "Radius", "equals", "MAB"),
        is_not=True,
    )
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Not)
    assert isinstance(result.operand, And)


def test_nested_or_inside_and():
    cond = _and(
        _or(
            _single("Protocol", "Radius", "equals", "Dot1X"),
            _single("Protocol", "Radius", "equals", "MAB"),
        ),
        _single("Called-Station-ID", "Radius", "startsWith", "00"),
    )
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, And)
    assert len(result.operands) == 2
    assert isinstance(result.operands[0], Or)


# ---------------------------------------------------------------------------
# REFERENCE resolution
# ---------------------------------------------------------------------------

def test_reference_resolves_from_library():
    lib = {
        "Wireless_802.1X": {
            "id": "lib-1",
            "name": "Wireless_802.1X",
            "description": "",
            "condition": _single("Protocol", "Radius", "equals", "Dot1X"),
        }
    }
    cond = _ref("Wireless_802.1X")
    result = normalize_ise_condition(cond, lib, [])
    assert isinstance(result, Predicate)
    assert result.op == Op.equals


def test_reference_is_not_wraps_resolved_in_not():
    lib = {
        "MyLib": {
            "id": "lib-1",
            "name": "MyLib",
            "description": "",
            "condition": _single("Protocol", "Radius", "equals", "Dot1X"),
        }
    }
    cond = _ref("MyLib", is_not=True)
    result = normalize_ise_condition(cond, lib, [])
    assert isinstance(result, Not)
    assert isinstance(result.operand, Predicate)


def test_unresolved_reference_returns_degenerate_and_warns():
    warnings: list[str] = []
    cond = _ref("NonExistentLib")
    result = normalize_ise_condition(cond, {}, warnings)
    assert isinstance(result, And)
    assert result.operands == []
    assert any("NonExistentLib" in w for w in warnings)


def test_reference_null_condition_returns_none():
    """Library entry with condition=None (match-all) resolves to None."""
    lib = {"MatchAll": {"id": "x", "name": "MatchAll", "description": "", "condition": None}}
    cond = _ref("MatchAll")
    result = normalize_ise_condition(cond, lib, [])
    assert result is None


# ---------------------------------------------------------------------------
# All 19 ISE operators — round-trip via _ise_op
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ise_op,expected", [
    ("contains",          Op.contains),
    ("endsWith",          Op.ends_with),
    ("equals",            Op.equals),
    ("greaterOrEquals",   Op.greater_than_or_equals),
    ("greaterThan",       Op.greater_than),
    ("in",                Op.in_),
    ("ipEquals",          Op.ip_equals),
    ("ipGreaterThan",     Op.ip_greater_than),
    ("ipLessThan",        Op.ip_less_than),
    ("ipNotEquals",       Op.ip_not_equals),
    ("lessOrEquals",      Op.less_than_or_equals),
    ("lessThan",          Op.less_than),
    ("matches",           Op.regex),
    ("notContains",       Op.not_contains),
    ("notEndsWith",       Op.not_ends_with),
    ("notEquals",         Op.not_equals),
    ("notIn",             Op.not_in),
    ("notStartsWith",     Op.not_starts_with),
    ("startsWith",        Op.starts_with),
])
def test_ise_op_mapping(ise_op, expected):
    assert _ise_op(ise_op) == expected


def test_unknown_operator_raises():
    with pytest.raises(ValueError, match="Unknown ISE operator"):
        _ise_op("TOTALLY_UNKNOWN_OP")


# ---------------------------------------------------------------------------
# IP operator predicates produced correctly
# ---------------------------------------------------------------------------

def test_ip_equals_predicate():
    cond = _single("NAS-IP-Address", "Radius", "ipEquals", "10.0.0.1")
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)
    assert result.op == Op.ip_equals


def test_not_in_predicate():
    cond = _single("Location", "Network", "notIn", "Branch")
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)
    assert result.op == Op.not_in


def test_matches_produces_regex_op():
    cond = _single("User-Name", "Radius", "matches", "^admin.*")
    result = normalize_ise_condition(cond, {}, [])
    assert isinstance(result, Predicate)
    assert result.op == Op.regex


# ---------------------------------------------------------------------------
# Unknown node type
# ---------------------------------------------------------------------------

def test_unknown_node_type_returns_none():
    cond = {"type": "UNKNOWN_TYPE", "is_not": False}
    assert normalize_ise_condition(cond, {}, []) is None
