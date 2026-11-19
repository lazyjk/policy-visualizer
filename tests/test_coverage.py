"""Anonymous coverage report (src/coverage.py, POST /api/coverage, CLI --coverage).

The report is meant to be shared, so the key test is a privacy regression:
no object name, description, condition value or attribute value from either
lab fixture may appear in it.
"""
import io
import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from api.main import app
from src import pgdump_parser
from src.cli import main as cli_main
from src.coverage import _predicates, coverage_report
from src.parser import parse
from src.pgdump_parser import raw_from_tables
from src.pgdump_reader import parse_copy_text
from src.policy_ir import build

FIXTURES = Path(__file__).parent / "fixtures"
XML = FIXTURES / "LabKitchenSink.xml"
COPY = FIXTURES / "pgdump" / "LabKitchenSink.copy.txt"

# Lab strings that are also generic schema words and so legitimately occur
# inside report keys (e.g. "Guest" within the "GuestUser" namespace, "Name"
# within the "@valueDispName" path shape).
_GENERIC_WORDS = {"Authentication", "Disconnect", "Guest", "Name"}


def _inputs():
    xml_raw = parse(XML)
    db_raw = raw_from_tables(parse_copy_text(COPY.read_text(encoding="utf-8")))
    return {"xml": xml_raw, "pgdump": db_raw}


@pytest.fixture(scope="module", params=["xml", "pgdump"])
def case(request):
    raw = _inputs()[request.param]
    ir = build(raw)
    return request.param, raw, ir, coverage_report(raw, ir)


def _sensitive_strings(ir) -> set[str]:
    out: set[str] = set()
    for coll in (ir.services, ir.role_mapping_policies, ir.enforcement_policies,
                 ir.enforcement_profiles, ir.roles, ir.auth_methods, ir.auth_sources):
        for o in coll.values():
            out.add(o.name)
            out.add(getattr(o, "description", "") or "")
    for p in ir.enforcement_profiles.values():
        for a in p.attributes:
            out.update((a.value, a.display_value))
    exprs = [s.match for s in ir.services.values()] + [
        r.when for p in [*ir.role_mapping_policies.values(), *ir.enforcement_policies.values()] for r in p.rules
    ]
    for e in exprs:
        for pred in _predicates(e):
            out.update((pred.rhs_raw, pred.rhs_display, pred.attribute))
    return {s for s in out if s and len(s) >= 4} - _GENERIC_WORDS


def test_report_leaks_no_names_or_values(case):
    _, _, ir, report = case
    text = json.dumps(report)
    leaks = sorted(s for s in _sensitive_strings(ir) if s in text)
    assert leaks == []


def test_report_contains_no_ip_addresses(case):
    text = json.dumps(case[3])
    assert re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text) == []


def test_auth_sources_are_anonymised(case):
    namespaces = case[3]["conditions"]["namespaces"]
    assert "Authorization:<source>" in namespaces
    assert not [n for n in namespaces if n.startswith("Authorization:") and n != "Authorization:<source>"]


def test_lab_counts(case):
    fmt, _, _, report = case
    assert report["source"]["format"] == fmt
    assert report["source"]["clearpass_version"] == ("6.11" if fmt == "xml" else None)
    assert report["services"]["total"] == 27
    assert report["services"]["by_type"] == {
        "APPLICATION": 5, "RADIUS": 16, "RADIUS_PROXY": 2, "TACACS": 3, "WEBAUTH": 1,
    }
    assert report["services"]["options"]["divider"] == 2
    assert report["conditions"]["unknown_operators"] == {}
    assert report["warnings"] == {}


def test_db_backup_reports_profile_types_the_export_lacks():
    raw = _inputs()["pgdump"]
    types = coverage_report(raw, build(raw))["profiles"]["by_type"]
    assert types["snmp"] == 1 and types["agent"] == 1


def test_uninterpreted_settings_reported_by_shape_only():
    raw = _inputs()["xml"]
    extras = coverage_report(raw, build(raw))["uninterpreted_settings"]
    assert "service:AcctFilterParamList/RulesCondition/@oper" in extras
    assert not any("[" in k for k in extras)


def test_unknown_operator_is_counted_and_categorised():
    raw = _inputs()["xml"]
    raw = {**raw, "roleMappings": [dict(p) for p in raw["roleMappings"]]}
    rule = json.loads(json.dumps(raw["roleMappings"][0]["rules"][0]))
    rule["expression"]["attributes"][0]["operator"] = "SOUNDS_LIKE"
    raw["roleMappings"][0] = {**raw["roleMappings"][0], "rules": [rule, *raw["roleMappings"][0]["rules"][1:]]}
    report = coverage_report(raw, build(raw))
    assert report["conditions"]["unknown_operators"] == {"SOUNDS_LIKE": 1}
    assert report["warnings"] == {"unknown_operator": 1}


def test_deterministic(case):
    _, raw, ir, report = case
    assert coverage_report(raw, ir) == report


client = TestClient(app)


def test_api_coverage_xml():
    res = client.post("/api/coverage", files={"file": ("lab.xml", io.BytesIO(XML.read_bytes()), "application/xml")})
    assert res.status_code == 200
    assert res.json()["services"]["total"] == 27


def test_api_coverage_pgdump(monkeypatch):
    tables = parse_copy_text(COPY.read_text(encoding="utf-8"))
    monkeypatch.setattr(pgdump_parser, "read_pgdump", lambda path: tables)
    res = client.post("/api/coverage", files={"file": ("lab.pgdump", io.BytesIO(b"PGDMP-x"), "application/octet-stream")})
    assert res.status_code == 200
    assert res.json()["source"]["format"] == "pgdump"


def test_api_coverage_rejects_ise():
    ise = (FIXTURES / "ISEPolicyConfig.xml").read_bytes()
    res = client.post("/api/coverage", files={"file": ("ise.xml", io.BytesIO(ise), "application/xml")})
    assert res.status_code == 422


def test_cli_coverage_stdout_is_json():
    result = CliRunner().invoke(cli_main, [str(XML), "--coverage"])  # click 8.2+: stderr kept separate
    assert result.exit_code == 0
    assert json.loads(result.stdout)["services"]["total"] == 27
