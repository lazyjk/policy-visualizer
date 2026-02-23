"""Tests for Phase 2: Condition Normalization."""
import pytest

from src.normalizer import And, Op, Or, Predicate, normalize, expr_to_label


def _raw_attr(name, type_, operator, value, displayValue=""):
    return {
        "name": name,
        "type": type_,
        "operator": operator,
        "value": value,
        "displayValue": displayValue or value,
    }


# ---------------------------------------------------------------------------
# Operator mapping
# ---------------------------------------------------------------------------

def test_op_from_raw_equals():
    assert Op.from_raw("EQUALS") == Op.equals


def test_op_from_raw_contains():
    assert Op.from_raw("CONTAINS") == Op.contains


def test_op_from_raw_unknown():
    with pytest.raises(ValueError):
        Op.from_raw("UNKNOWN_OP")


# ---------------------------------------------------------------------------
# Single predicate unwrapping
# ---------------------------------------------------------------------------

def test_single_predicate_unwrapped():
    raw = {
        "operator": "OR",
        "displayOperator": "MATCHES_ANY",
        "attributes": [
            _raw_attr("memberOf", "Authorization:AD", "EQUALS", "CN=Group,DC=msu")
        ],
    }
    result = normalize(raw)
    assert isinstance(result, Predicate)
    assert result.op == Op.equals
    assert result.attribute == "memberOf"


# ---------------------------------------------------------------------------
# AND / OR tree construction
# ---------------------------------------------------------------------------

def test_matches_all_becomes_and():
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            _raw_attr("Aruba-Essid-Name", "Radius:Aruba", "CONTAINS", "Secure"),
            _raw_attr("User-Name", "Radius:IETF", "CONTAINS", "student.state.edu"),
        ],
    }
    result = normalize(raw)
    assert isinstance(result, And)
    assert len(result.operands) == 2
    assert all(isinstance(o, Predicate) for o in result.operands)


def test_matches_any_becomes_or():
    raw = {
        "operator": "OR",
        "displayOperator": "MATCHES_ANY",
        "attributes": [
            _raw_attr("Role", "Tips", "EQUALS", "Students"),
            _raw_attr("Role", "Tips", "EQUALS", "Faculty-Staff"),
        ],
    }
    result = normalize(raw)
    assert isinstance(result, Or)
    assert len(result.operands) == 2


# ---------------------------------------------------------------------------
# Predicate correctness
# ---------------------------------------------------------------------------

def test_predicate_fields():
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            _raw_attr("Aruba-Essid-Name", "Radius:Aruba", "CONTAINS", "Secure", "Secure"),
        ],
    }
    result = normalize(raw)
    assert isinstance(result, Predicate)
    assert result.namespace == "Radius:Aruba"
    assert result.rhs_raw == "Secure"
    assert result.rhs_display == "Secure"


def test_normalize_none_returns_none():
    assert normalize(None) is None


# ---------------------------------------------------------------------------
# Label generation
# ---------------------------------------------------------------------------

def test_expr_to_label_predicate():
    raw = {
        "operator": "OR",
        "displayOperator": "MATCHES_ANY",
        "attributes": [
            _raw_attr("Role", "Tips", "EQUALS", "Bypass", "Bypass"),
        ],
    }
    label = expr_to_label(normalize(raw))
    assert "Bypass" in label
    assert "equals" in label


def test_expr_to_label_truncated():
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            _raw_attr("A", "T", "EQUALS", "x" * 100),
            _raw_attr("B", "T", "EQUALS", "y" * 100),
        ],
    }
    label = expr_to_label(normalize(raw), max_len=60)
    assert len(label) <= 60


def test_expr_to_label_none():
    label = expr_to_label(None)
    assert "no condition" in label
