"""Where-used / unused-object analysis (src/xref.py, POST /api/xref).

The lab DB backup is the oracle: after the v2 re-wiring, exactly two of its
test profiles are still referenced by no policy or service.
"""
import copy
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src import pgdump_parser
from src.parser import parse
from src.pgdump_parser import raw_from_tables
from src.pgdump_reader import parse_copy_text
from src.policy_ir import build
from src.xref import build_xref, is_builtin

FIXTURES = Path(__file__).parent / "fixtures"
XML = FIXTURES / "LabKitchenSink.xml"
COPY = FIXTURES / "pgdump" / "LabKitchenSink.copy.txt"

# Profiles configured in the lab but referenced by no policy or service.
LAB_UNUSED_PROFILES = {
    "kit-lab-wired 802.1X Wired Default Profile",
    "test-generic-application-enforcment",
}


@pytest.fixture(scope="module")
def tables():
    return parse_copy_text(COPY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def xml_ir():
    return build(parse(XML))


@pytest.fixture(scope="module")
def db_ir(tables):
    return build(raw_from_tables(tables))


def _obj(x, kind, name):
    return next(o for o in x["objects"] if o["kind"] == kind and o["name"] == name)


def test_db_backup_finds_the_lab_orphans(db_ir):
    x = build_xref(db_ir)
    assert x["complete"] is True and x["source_format"] == "pgdump"
    unused = {f["name"] for f in x["findings"]
              if f["code"] == "unused" and f["kind"] == "enforcement_profile" and not f["builtin"]}
    assert unused == LAB_UNUSED_PROFILES


def test_xml_export_has_no_orphans_and_says_it_is_incomplete(xml_ir):
    x = build_xref(xml_ir)
    assert x["complete"] is False and x["source_format"] == "xml"
    assert [f for f in x["findings"] if f["code"] == "unused"] == []


def test_profiler_coa_profile_counts_as_used(db_ir):
    o = _obj(build_xref(db_ir), "enforcement_profile", "test-dynauth-enforcement-profile")
    assert o["status"] == "used"
    assert {"kind": "service", "id": o["used_by"][0]["id"], "name": "test-wired-id-only",
            "where": "profiler CoA"} in o["used_by"]


def test_inner_eap_methods_count_as_used(xml_ir):
    x = build_xref(xml_ir)
    assert not [f for f in x["findings"] if f["kind"] == "auth_method"]


def test_used_by_lists_rules_and_defaults(xml_ir):
    o = _obj(build_xref(xml_ir), "enforcement_profile", "[Allow Access Profile]")
    wheres = {(u["name"], u["where"]) for u in o["used_by"]}
    assert ("[Sample Allow Access Policy]", "default profile") in wheres
    assert ("[Sample Allow Access Policy]", "rule 1") in wheres


def test_only_disabled_when_the_sole_enabled_user_is_switched_off(xml_ir):
    ir = copy.deepcopy(xml_ir)
    # [Admin Network Login Policy] is shared by a disabled built-in service and
    # one enabled lab service; disable the latter too.
    for svc in ir.services.values():
        if svc.name.startswith("test-cppm-admin-ad"):
            svc.enabled = False
    x = build_xref(ir)
    assert _obj(x, "enforcement_policy", "[Admin Network Login Policy]")["status"] == "only_disabled"
    assert any(f["code"] == "only_disabled" and f["name"] == "[TACACS+ Super Admin]" for f in x["findings"])


def test_role_findings(xml_ir):
    x = build_xref(xml_ir)
    codes = {(f["code"], f["name"]) for f in x["findings"] if f["kind"] == "role"}
    assert ("role_assigned_never_tested", "[Other]") in codes
    assert ("role_tested_never_assigned", "[User Authenticated]") in codes


def test_deterministic(db_ir):
    assert build_xref(db_ir) == build_xref(db_ir)


def test_is_builtin():
    assert is_builtin("[Allow Access Profile]")
    assert not is_builtin("test-cisco-dacl")


client = TestClient(app)


def test_api_xref_xml():
    res = client.post("/api/xref", files={"file": ("lab.xml", io.BytesIO(XML.read_bytes()), "application/xml")})
    assert res.status_code == 200
    body = res.json()
    assert body["complete"] is False
    assert {"kind", "id", "name", "builtin", "status", "used_by"} <= set(body["objects"][0])


def test_api_xref_pgdump(monkeypatch, tables):
    monkeypatch.setattr(pgdump_parser, "read_pgdump", lambda path: tables)
    res = client.post("/api/xref", files={"file": ("lab.pgdump", io.BytesIO(b"PGDMP-fake"), "application/octet-stream")})
    assert res.status_code == 200
    unused = {f["name"] for f in res.json()["findings"] if f["code"] == "unused" and not f["builtin"]
              and f["kind"] == "enforcement_profile"}
    assert unused == LAB_UNUSED_PROFILES


def test_api_xref_rejects_ise():
    ise = (FIXTURES / "ISEPolicyConfig.xml").read_bytes()
    res = client.post("/api/xref", files={"file": ("ise.xml", io.BytesIO(ise), "application/xml")})
    assert res.status_code == 422
