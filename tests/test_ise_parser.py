"""Tests for ISE XML Parser (src/ise_parser.py)."""
from pathlib import Path

import pytest

from src.ise_parser import ise_parse

FIXTURE = Path(__file__).parent / "fixtures" / "ISEPolicyConfig.xml"


@pytest.fixture(scope="module")
def raw():
    return ise_parse(FIXTURE)


# ---------------------------------------------------------------------------
# Format marker
# ---------------------------------------------------------------------------

def test_format_marker(raw):
    assert raw["format"] == "ise"


# ---------------------------------------------------------------------------
# Policy set counts and types
# ---------------------------------------------------------------------------

def test_policy_set_count(raw):
    # 2 RADIUS + 1 TACACS = 3
    assert len(raw["policy_sets"]) == 3


def test_radius_policy_sets(raw):
    radius = [ps for ps in raw["policy_sets"] if ps["set_type"] == "RADIUS"]
    assert len(radius) == 2


def test_tacacs_policy_set(raw):
    tacacs = [ps for ps in raw["policy_sets"] if ps["set_type"] == "TACACS"]
    assert len(tacacs) == 1


def test_policy_set_names(raw):
    names = {ps["name"] for ps in raw["policy_sets"]}
    assert "Test-DOT1X" in names
    assert "Default" in names


def test_policy_sets_sorted_by_rank(raw):
    ranks = [ps["rank"] for ps in raw["policy_sets"]]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Policy set conditions
# ---------------------------------------------------------------------------

def test_dot1x_has_match_condition(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    assert dot1x["match_condition"] is not None
    assert dot1x["match_condition"]["type"] == "AND_BLOCK"


def test_default_has_match_all(raw):
    default_radius = next(
        ps for ps in raw["policy_sets"] if ps["name"] == "Default" and ps["set_type"] == "RADIUS"
    )
    assert default_radius["match_condition"] is None


# ---------------------------------------------------------------------------
# Authentication rules
# ---------------------------------------------------------------------------

def test_dot1x_authen_rules(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    assert len(dot1x["authen_rules"]) == 2
    names = [r["name"] for r in dot1x["authen_rules"]]
    assert "LAB-AD-AUTH" in names
    assert "Default" in names


def test_authen_rules_sorted_by_rank(raw):
    for ps in raw["policy_sets"]:
        ranks = [r["rank"] for r in ps["authen_rules"]]
        assert ranks == sorted(ranks)


def test_authen_rule_storename(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    lab_ad = next(r for r in dot1x["authen_rules"] if r["name"] == "LAB-AD-AUTH")
    assert lab_ad["storename"] == "lab-ad"
    assert lab_ad["storetype"] == "IdentityStore"


def test_authen_rule_fail_actions(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    lab_ad = next(r for r in dot1x["authen_rules"] if r["name"] == "LAB-AD-AUTH")
    assert lab_ad["authen_fail_action"] == "REJECT"
    assert lab_ad["user_not_found_action"] == "REJECT"


def test_mab_rule_has_continue(raw):
    default_radius = next(
        ps for ps in raw["policy_sets"] if ps["name"] == "Default" and ps["set_type"] == "RADIUS"
    )
    mab = next(r for r in default_radius["authen_rules"] if r["name"] == "MAB")
    assert mab["user_not_found_action"] == "CONTINUE"


def test_authen_rule_match_all_condition(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    default_rule = next(r for r in dot1x["authen_rules"] if r["name"] == "Default")
    assert default_rule["condition"] is None


def test_authen_rule_or_block(raw):
    default_radius = next(
        ps for ps in raw["policy_sets"] if ps["name"] == "Default" and ps["set_type"] == "RADIUS"
    )
    mab = next(r for r in default_radius["authen_rules"] if r["name"] == "MAB")
    # MAB condition is AND_BLOCK wrapping an OR_BLOCK
    assert mab["condition"] is not None
    assert mab["condition"]["type"] == "AND_BLOCK"
    inner = mab["condition"]["children"][0]
    assert inner["type"] == "OR_BLOCK"


# ---------------------------------------------------------------------------
# Authorization rules
# ---------------------------------------------------------------------------

def test_dot1x_author_rules_count(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    assert len(dot1x["author_rules"]) == 2


def test_disabled_author_rules_present_in_raw(raw):
    # Parser keeps DISABLED rules; filtering happens in policy IR
    default_radius = next(
        ps for ps in raw["policy_sets"] if ps["name"] == "Default" and ps["set_type"] == "RADIUS"
    )
    statuses = {r["status"] for r in default_radius["author_rules"]}
    assert "DISABLED" in statuses
    assert "ENABLED" in statuses


def test_author_rule_profiles(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    allow_rule = next(r for r in dot1x["author_rules"] if r["name"] == "Allow-from-AD")
    assert "PermitAccess" in allow_rule["profiles"]


def test_author_rule_match_all(raw):
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    default_rule = next(r for r in dot1x["author_rules"] if r["name"] == "Default")
    assert default_rule["condition"] is None


# ---------------------------------------------------------------------------
# TACACS commandsets
# ---------------------------------------------------------------------------

def test_tacacs_author_rule_commandsets(raw):
    tacacs = next(ps for ps in raw["policy_sets"] if ps["set_type"] == "TACACS")
    default_rule = tacacs["author_rules"][0]
    assert "DenyAllCommands" in default_rule["commandsets"]
    assert "Deny All Shell Profile" in default_rule["profiles"]


# ---------------------------------------------------------------------------
# Library conditions
# ---------------------------------------------------------------------------

def test_library_condition_count(raw):
    assert len(raw["library_conditions"]) >= 10


def test_library_condition_wireless_802_1x(raw):
    lib = raw["library_conditions"]
    assert "Wireless_802.1X" in lib
    cond = lib["Wireless_802.1X"]["condition"]
    assert cond is not None
    assert cond["type"] == "AND_BLOCK"


def test_library_condition_reference_resolved_by_name(raw):
    # REFERENCE nodes use refId = library condition name
    dot1x = next(ps for ps in raw["policy_sets"] if ps["name"] == "Test-DOT1X")
    match = dot1x["match_condition"]
    child = match["children"][0]
    assert child["type"] == "REFERENCE"
    assert child["ref_id"] == "Wireless_802.1X"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def test_profiles_present(raw):
    assert "PermitAccess" in raw["profiles"]
    assert "DenyAccess" in raw["profiles"]


def test_permit_access_type(raw):
    assert raw["profiles"]["PermitAccess"]["access_type"] == "ACCESS_ACCEPT"


def test_deny_access_type(raw):
    assert raw["profiles"]["DenyAccess"]["access_type"] == "ACCESS_REJECT"


def test_tacacs_profile_type(raw):
    assert raw["profiles"]["Deny All Shell Profile"]["profile_type"] == "tacacs"


def test_commandset_profile_type(raw):
    assert raw["profiles"]["DenyAllCommands"]["profile_type"] == "commandset"
