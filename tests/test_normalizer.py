"""Tests for Phase 2: Condition Normalization."""
import pytest

from src.normalizer import And, Op, Or, Predicate, normalize, expr_to_label, expr_to_node_label


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


def test_op_belongs_to_group():
    assert Op.from_raw("BELONGS_TO_GROUP") == Op.belongs_to_group


def test_op_not_ends_with():
    assert Op.from_raw("NOT_ENDS_WITH") == Op.not_ends_with


def test_op_matches_any_predicate_maps_to_in():
    # MATCHES_ANY as a per-predicate operator (not expression-level) → in
    assert Op.from_raw("MATCHES_ANY") == Op.in_


def test_op_begins_with_maps_to_starts_with():
    assert Op.from_raw("BEGINS_WITH") == Op.starts_with


def test_op_matches_regex():
    assert Op.from_raw("MATCHES_REGEX") == Op.regex


def test_op_not_matches_regex():
    assert Op.from_raw("NOT_MATCHES_REGEX") == Op.not_regex


def test_op_belongs_to_alias():
    assert Op.from_raw("BELONGS_TO") == Op.belongs_to_group


def test_op_less_than_or_equals():
    assert Op.from_raw("LESS_THAN_OR_EQUALS") == Op.less_than_or_equals


def test_op_greater_than_or_equals():
    assert Op.from_raw("GREATER_THAN_OR_EQUALS") == Op.greater_than_or_equals


def test_op_equals_ignore_case():
    assert Op.from_raw("EQUALS_IGNORE_CASE") == Op.equals_ignore_case


def test_op_not_begins_with():
    assert Op.from_raw("NOT_BEGINS_WITH") == Op.not_starts_with


def test_op_not_belongs_to_group():
    assert Op.from_raw("NOT_BELONGS_TO_GROUP") == Op.not_belongs_to_group


def test_op_not_belongs_to_alias():
    assert Op.from_raw("NOT_BELONGS_TO") == Op.not_belongs_to_group


def test_op_not_equals_ignore_case():
    assert Op.from_raw("NOT_EQUALS_IGNORE_CASE") == Op.not_equals_ignore_case


def test_op_matches_exact():
    assert Op.from_raw("MATCHES_EXACT") == Op.matches_exact


def test_op_not_matches_exact():
    assert Op.from_raw("NOT_MATCHES_EXACT") == Op.not_matches_exact


def test_op_not_matches_all():
    assert Op.from_raw("NOT_MATCHES_ALL") == Op.not_matches_all


def test_op_not_matches_any():
    assert Op.from_raw("NOT_MATCHES_ANY") == Op.not_matches_any


def test_op_in_range():
    assert Op.from_raw("IN_RANGE") == Op.in_range


# ---------------------------------------------------------------------------
# Single predicate unwrapping
# ---------------------------------------------------------------------------

def test_single_predicate_unwrapped():
    raw = {
        "operator": "OR",
        "displayOperator": "MATCHES_ANY",
        "attributes": [
            _raw_attr("memberOf", "Authorization:Directory", "EQUALS", "CN=Group,DC=example")
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


# ---------------------------------------------------------------------------
# expr_to_node_label — displayValue preference for numeric RHS
# ---------------------------------------------------------------------------

def test_node_label_uses_display_for_numeric_rhs():
    """Numeric raw value should use displayValue in decision node labels."""
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            {
                "name": "NAS-Port-Type",
                "type": "Radius:IETF",
                "operator": "EQUALS",
                "value": "19",
                "displayValue": "Wireless-802.11 (19)",
            }
        ],
    }
    label = expr_to_node_label(normalize(raw))
    assert "Wireless-802.11 (19)" in label
    assert "19\n" not in label  # bare numeric must not appear as its own line


def test_node_label_uses_display_for_numeric_csv_rhs():
    """Comma-separated numeric raw value should use displayValue."""
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            {
                "name": "Service-Type",
                "type": "Radius:IETF",
                "operator": "BELONGS_TO",
                "value": "1,2,8",
                "displayValue": "Login-User (1), Framed-User (2), Authenticate-Only (8)",
            }
        ],
    }
    label = expr_to_node_label(normalize(raw))
    assert "Login-User (1)" in label
    assert label.count("1,2,8") == 0


def test_node_label_uses_raw_for_string_rhs():
    """String raw values should not be replaced by displayValue."""
    raw = {
        "operator": "and",
        "displayOperator": "MATCHES_ALL",
        "attributes": [
            {
                "name": "UserDN",
                "type": "Authorization:BPS7.Local",
                "operator": "CONTAINS",
                "value": "OU=BSD7-User-Student",
                "displayValue": "OU=BSD7-User-Student",
            }
        ],
    }
    label = expr_to_node_label(normalize(raw))
    assert "OU=BSD7-User-Student" in label
