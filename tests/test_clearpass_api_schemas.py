"""Unit tests for src/clearpass_api_schemas.py.

Verifies that each Pydantic model:
  - accepts the canonical field names
  - accepts all known alternative field names (firmware variant coverage)
  - always emits a single canonical output shape
"""
from __future__ import annotations

import pytest

from src.clearpass_api_schemas import (
    CPAuthItem,
    CPCondition,
    CPEnforcementPolicy,
    CPEnforcementPolicyListItem,
    CPEnforcementPolicyRule,
    CPEnforcementProfileItem,
    CPLinkedPolicy,
    CPRoleItem,
    CPRoleMappingListItem,
    CPRoleMappingPolicy,
    CPRoleMappingRule,
    CPService,
    CPServiceListItem,
)


# ---------------------------------------------------------------------------
# CPCondition — field name normalization
# ---------------------------------------------------------------------------

class TestCPCondition:
    def test_canonical_fields(self):
        c = CPCondition.model_validate(
            {"namespace": "Radius:IETF", "attribute": "Service-Type", "operator": "EQUALS", "value": "Framed-User"}
        )
        assert c.namespace == "Radius:IETF"
        assert c.attribute == "Service-Type"
        assert c.operator == "EQUALS"
        assert c.value == "Framed-User"

    def test_rest_api_variant(self):
        """ClearPass REST API most common format: type/name/oper/value."""
        c = CPCondition.model_validate(
            {"type": "Authorization:MSU-AD", "name": "memberOf", "oper": "CONTAINS", "value": "Staff"}
        )
        assert c.namespace == "Authorization:MSU-AD"
        assert c.attribute == "memberOf"
        assert c.operator == "CONTAINS"
        assert c.value == "Staff"

    def test_attr_oper_variant(self):
        """Some firmware uses attr_oper / attr_value."""
        c = CPCondition.model_validate(
            {"type": "Radius:IETF", "attr_name": "NAS-Port-Type", "attr_oper": "EQUALS", "attr_value": "Wireless-802.11"}
        )
        assert c.namespace == "Radius:IETF"
        assert c.attribute == "NAS-Port-Type"
        assert c.operator == "EQUALS"
        assert c.value == "Wireless-802.11"

    def test_variant_fields_stripped_from_output(self):
        """Variant field names (oper, type, name) must not appear in canonical output."""
        c = CPCondition.model_validate(
            {"type": "NS", "name": "attr", "oper": "EQUALS", "value": "v"}
        )
        d = c.model_dump()
        assert "type" not in d
        assert "name" not in d
        assert "oper" not in d

    def test_empty_input_returns_defaults(self):
        c = CPCondition.model_validate({})
        assert c.namespace == ""
        assert c.attribute == ""
        assert c.operator == ""
        assert c.value == ""


# ---------------------------------------------------------------------------
# CPAuthItem
# ---------------------------------------------------------------------------

class TestCPAuthItem:
    def test_dict_input(self):
        item = CPAuthItem.model_validate({"id": "r1", "name": "Employee"})
        assert item.id == "r1"
        assert item.name == "Employee"

    def test_string_input(self):
        item = CPAuthItem.model_validate("PEAP Mschapv2")
        assert item.id == "PEAP Mschapv2"
        assert item.name == "PEAP Mschapv2"

    def test_id_falls_back_to_name(self):
        item = CPAuthItem.model_validate({"name": "Employee"})
        assert item.name == "Employee"
        assert item.id == "Employee"


# ---------------------------------------------------------------------------
# CPLinkedPolicy
# ---------------------------------------------------------------------------

class TestCPLinkedPolicy:
    def test_dict_input(self):
        p = CPLinkedPolicy.model_validate({"id": "p1", "name": "Corp WiFi RM"})
        assert p.id == "p1"
        assert p.name == "Corp WiFi RM"

    def test_string_input(self):
        p = CPLinkedPolicy.model_validate("Corp WiFi RM")
        assert p.id == ""
        assert p.name == "Corp WiFi RM"

    def test_empty_dict(self):
        p = CPLinkedPolicy.model_validate({})
        assert p.id == ""
        assert p.name == ""


# ---------------------------------------------------------------------------
# CPServiceListItem — service_type normalization
# ---------------------------------------------------------------------------

class TestCPServiceListItem:
    def test_type_field(self):
        item = CPServiceListItem.model_validate({"id": "s1", "name": "Corp WiFi", "type": "RADIUS"})
        assert item.service_type == "RADIUS"

    def test_template_type_field(self):
        item = CPServiceListItem.model_validate({"id": "s2", "name": "Corp VPN", "template_type": "TACACS"})
        assert item.service_type == "TACACS"

    def test_service_type_field(self):
        item = CPServiceListItem.model_validate({"id": "s3", "name": "Wired", "service_type": "RADIUS"})
        assert item.service_type == "RADIUS"

    def test_type_takes_priority_over_service_type(self):
        item = CPServiceListItem.model_validate({"type": "TACACS", "service_type": "RADIUS"})
        assert item.service_type == "TACACS"


# ---------------------------------------------------------------------------
# CPEnforcementProfileItem
# ---------------------------------------------------------------------------

class TestCPEnforcementProfileItem:
    def test_basic(self):
        item = CPEnforcementProfileItem.model_validate(
            {"id": "ep1", "name": "Allow Access Profile", "profile_type": "radius_accept"}
        )
        assert item.profile_type == "radius_accept"

    def test_default_profile_type(self):
        item = CPEnforcementProfileItem.model_validate({"id": "ep2", "name": "Some Profile"})
        assert item.profile_type == "radius_accept"


# ---------------------------------------------------------------------------
# CPRoleMappingRule — conditions and stop_if_match normalization
# ---------------------------------------------------------------------------

class TestCPRoleMappingRule:
    def test_condition_singular_normalized(self):
        """REST API uses 'condition' (singular); should be normalized to 'conditions'."""
        rule = CPRoleMappingRule.model_validate({
            "id": "r1",
            "name": "Rule 1",
            "condition": [{"type": "Radius:IETF", "name": "Service-Type", "oper": "EQUALS", "value": "Framed-User"}],
            "roles": [{"id": "role1", "name": "Employee"}],
        })
        assert len(rule.conditions) == 1
        assert rule.conditions[0].namespace == "Radius:IETF"
        assert rule.conditions[0].operator == "EQUALS"

    def test_conditions_plural_accepted(self):
        rule = CPRoleMappingRule.model_validate({
            "conditions": [{"namespace": "Radius:IETF", "attribute": "NAS-Port-Type", "operator": "EQUALS", "value": "15"}],
        })
        assert len(rule.conditions) == 1

    def test_stop_if_match_bool(self):
        r_stop = CPRoleMappingRule.model_validate({"stop_if_match": True})
        r_cont = CPRoleMappingRule.model_validate({"stop_if_match": False})
        assert r_stop.stop_if_match is True
        assert r_cont.stop_if_match is False

    def test_flow_on_match_fallback(self):
        """Policy IR format: flow.on_match should populate stop_if_match."""
        r_stop = CPRoleMappingRule.model_validate({"flow": {"on_match": "stop"}})
        r_cont = CPRoleMappingRule.model_validate({"flow": {"on_match": "continue"}})
        assert r_stop.stop_if_match is True
        assert r_cont.stop_if_match is False

    def test_stop_if_match_defaults_true(self):
        r = CPRoleMappingRule.model_validate({})
        assert r.stop_if_match is True


# ---------------------------------------------------------------------------
# CPRoleMappingPolicy — default_role normalization
# ---------------------------------------------------------------------------

class TestCPRoleMappingPolicy:
    def test_default_role_object(self):
        p = CPRoleMappingPolicy.model_validate({
            "id": "rm1",
            "name": "Corp RM",
            "rules": [],
            "default_role": {"id": "role-guest", "name": "Guest"},
        })
        assert p.default_role.id == "role-guest"
        assert p.default_role.name == "Guest"

    def test_default_role_flat_fields(self):
        """Some ClearPass versions use flat default_role_id / default_role_name."""
        p = CPRoleMappingPolicy.model_validate({
            "id": "rm1",
            "name": "Corp RM",
            "rules": [],
            "default_role_id": "role-guest",
            "default_role_name": "Guest",
        })
        assert p.default_role.id == "role-guest"
        assert p.default_role.name == "Guest"

    def test_rules_conditions_normalized(self):
        p = CPRoleMappingPolicy.model_validate({
            "id": "rm1",
            "name": "Test",
            "rules": [
                {
                    "id": "rule1",
                    "condition": [{"type": "Radius:IETF", "name": "NAS-Port-Type", "oper": "EQUALS", "value": "15"}],
                    "roles": [{"id": "r1", "name": "Employee"}],
                }
            ],
        })
        assert len(p.rules) == 1
        assert p.rules[0].conditions[0].namespace == "Radius:IETF"


# ---------------------------------------------------------------------------
# CPEnforcementPolicyRule — profile name/id and stop_if_match normalization
# ---------------------------------------------------------------------------

class TestCPEnforcementPolicyRule:
    def test_rest_api_profile_names(self):
        rule = CPEnforcementPolicyRule.model_validate({
            "enforcement_profile_names": ["[Allow Access Profile]"],
            "enforcement_profile_ids": [],
        })
        assert rule.enforcement_profile_names == ["[Allow Access Profile]"]

    def test_policy_ir_then_fallback(self):
        """Policy IR format: then.profile_names / then.profile_ids."""
        rule = CPEnforcementPolicyRule.model_validate({
            "then": {"profile_names": ["[Deny Access Profile]"], "profile_ids": ["ep-deny"]},
        })
        assert rule.enforcement_profile_names == ["[Deny Access Profile]"]
        assert rule.enforcement_profile_ids == ["ep-deny"]

    def test_stop_if_match_from_flow(self):
        r = CPEnforcementPolicyRule.model_validate({"flow": {"on_match": "continue"}})
        assert r.stop_if_match is False


# ---------------------------------------------------------------------------
# CPEnforcementPolicy — default profile normalization
# ---------------------------------------------------------------------------

class TestCPEnforcementPolicy:
    def test_default_profile_string(self):
        """Most common: default_enforcement_profile is a single string."""
        p = CPEnforcementPolicy.model_validate({
            "id": "ep1", "name": "Corp Enforcement", "rules": [],
            "default_enforcement_profile": "[Deny Access Profile]",
        })
        assert p.default_enforcement_profile_names == ["[Deny Access Profile]"]

    def test_default_profile_array(self):
        p = CPEnforcementPolicy.model_validate({
            "id": "ep1", "name": "Corp Enforcement", "rules": [],
            "default_enforcement_profiles": ["[Allow Access Profile]", "[Post Auth]"],
        })
        assert p.default_enforcement_profile_names == ["[Allow Access Profile]", "[Post Auth]"]

    def test_default_profile_from_default_object(self):
        """Policy IR format: default.profile_names / default.profile_ids."""
        p = CPEnforcementPolicy.model_validate({
            "id": "ep1", "name": "Corp Enforcement", "rules": [],
            "default": {
                "profile_names": ["[Deny Access Profile]"],
                "profile_ids": ["deny-id"],
            },
        })
        assert p.default_enforcement_profile_names == ["[Deny Access Profile]"]
        assert p.default_enforcement_profile_ids == ["deny-id"]

    def test_default_profile_ids_direct(self):
        p = CPEnforcementPolicy.model_validate({
            "default_enforcement_profile": "[Allow Access Profile]",
            "default_enforcement_profile_ids": ["allow-id"],
        })
        assert p.default_enforcement_profile_ids == ["allow-id"]

    def test_empty_defaults(self):
        p = CPEnforcementPolicy.model_validate({"id": "ep1", "name": "Test", "rules": []})
        assert p.default_enforcement_profile_names == []
        assert p.default_enforcement_profile_ids == []


# ---------------------------------------------------------------------------
# CPService — all field name normalizations
# ---------------------------------------------------------------------------

class TestCPService:
    def test_type_field_to_service_type(self):
        s = CPService.model_validate({"type": "TACACS"})
        assert s.service_type == "TACACS"
        d = s.model_dump()
        assert "type" not in d

    def test_template_type_field(self):
        s = CPService.model_validate({"template_type": "RADIUS"})
        assert s.service_type == "RADIUS"

    def test_rules_conditions_field(self):
        s = CPService.model_validate({
            "rules_conditions": [{"type": "Radius:IETF", "name": "NAS-Port-Type", "oper": "EQUALS", "value": "15"}]
        })
        assert len(s.rules_conditions) == 1
        assert s.rules_conditions[0].namespace == "Radius:IETF"

    def test_conditions_field_fallback(self):
        s = CPService.model_validate({
            "conditions": [{"namespace": "Radius:IETF", "attribute": "NAS-Port-Type", "operator": "EQUALS", "value": "15"}]
        })
        assert len(s.rules_conditions) == 1

    def test_authentication_methods_alt_field(self):
        s = CPService.model_validate({
            "auth_methods": [{"id": "m1", "name": "PEAP"}]
        })
        assert len(s.authentication_methods) == 1
        assert s.authentication_methods[0].name == "PEAP"

    def test_authentication_sources_alt_fields(self):
        s = CPService.model_validate({
            "authorization_sources": [{"id": "src1", "name": "LDAP"}]
        })
        assert len(s.authentication_sources) == 1

    def test_role_mapping_policy_string(self):
        s = CPService.model_validate({"role_mapping_policy": "Corp WiFi RM"})
        assert s.role_mapping_policy.name == "Corp WiFi RM"

    def test_enf_policy_alt_fields(self):
        s = CPService.model_validate({"enforcement_policy": "Corp WiFi Enforcement"})
        assert s.enf_policy.name == "Corp WiFi Enforcement"

        s2 = CPService.model_validate({"authorization_policy": "Corp WiFi Enforcement"})
        assert s2.enf_policy.name == "Corp WiFi Enforcement"

    def test_full_service_roundtrip(self):
        """A realistic service dict normalizes to all canonical fields."""
        raw = {
            "id": "svc-1",
            "name": "Corp WiFi",
            "type": "RADIUS",
            "description": "Main RADIUS service",
            "rules_conditions": [
                {"type": "Radius:IETF", "name": "NAS-Port-Type", "oper": "EQUALS", "value": "19"}
            ],
            "rules_match_type": "MATCHES_ALL",
            "authentication_methods": [{"id": "m1", "name": "EAP-TLS"}],
            "authentication_sources": [{"id": "src1", "name": "Internal Users"}],
            "role_mapping_policy": {"id": "rm1", "name": "Corp WiFi RM"},
            "enf_policy": {"id": "ep1", "name": "Corp WiFi Enforcement"},
        }
        s = CPService.model_validate(raw)
        assert s.id == "svc-1"
        assert s.service_type == "RADIUS"
        assert s.rules_match_type == "MATCHES_ALL"
        assert s.role_mapping_policy.id == "rm1"
        assert s.enf_policy.id == "ep1"
        d = s.model_dump()
        assert "type" not in d
        assert d["service_type"] == "RADIUS"
