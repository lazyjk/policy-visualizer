"""ClearPass DB backup (.pgdump) input.

Most tests run against tests/fixtures/pgdump/LabKitchenSink.copy.txt: the
allow-listed tables of the lab's tipsdb backup as COPY text, secrets masked
and identifying values sanitized (tools/extract_pgdump_fixture.py). It comes
from the same appliance as LabKitchenSink.xml, which makes the XML <-> DB
parity tests possible.

Tests that need pg_restore and the real (git-ignored) backup skip when either
is missing.
"""
import dataclasses
import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src import pgdump_parser
from src.flow_ir import compile_service
from src.parser import parse
from src.pgdump_parser import HIDDEN_VALUE, raw_from_tables
from src.pgdump_reader import (
    ALLOWED_COLUMNS,
    FORBIDDEN_TABLE_PATTERNS,
    PgRestoreNotFound,
    find_pg_restore,
    format_copy_text,
    is_pgdump,
    parse_copy_text,
)
from src.pgdump_rules import policy_rules, service_match
from src.policy_details import build_clearpass_details
from src.policy_ir import build

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
COPY_FIXTURE = FIXTURES / "pgdump" / "LabKitchenSink.copy.txt"
XML_FIXTURE = FIXTURES / "LabKitchenSink.xml"
REAL_DUMP = ROOT / "reference-files" / "kitchen-sinkv2tipsdb.pgdump"


@pytest.fixture(scope="module")
def tables():
    return parse_copy_text(COPY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw(tables):
    return raw_from_tables(tables)


@pytest.fixture(scope="module")
def db_ir(raw):
    return build(raw, source_file="lab.pgdump")


@pytest.fixture(scope="module")
def xml_ir():
    return build(parse(XML_FIXTURE), source_file=str(XML_FIXTURE))


def _svc(ir, name):
    return next(s for s in ir.services.values() if s.name == name)


def _profile(ir, name):
    return next(p for p in ir.enforcement_profiles.values() if p.name == name)


# ---------------------------------------------------------------------------
# Reader: allow-list and COPY text
# ---------------------------------------------------------------------------

def test_allow_list_never_names_a_forbidden_table():
    for table in ALLOWED_COLUMNS:
        for pattern in FORBIDDEN_TABLE_PATTERNS:
            assert not re.search(pattern, table), f"{table} matches forbidden pattern {pattern!r}"


@pytest.mark.parametrize("table,column", [
    ("tips_proxy_server", "shared_secret"),
    ("tips_proxy_server", "host_name"),
    ("tips_auth_sources", "extras"),
    ("tips_auth_sources", "restriction_xml"),
    ("tips_nad_group", "members"),
])
def test_secret_or_network_columns_not_allowed(table, column):
    assert column not in ALLOWED_COLUMNS[table]


def test_parse_copy_text_escapes_nulls_and_column_filter():
    text = (
        "COPY public.tips_role (id, name, description, org_id) FROM stdin;\n"
        "1\tA\\tB\t\\N\t7\n"
        "2\tline1\\nline2\tback\\\\slash \\101\\x42\t7\n"
        "\\.\n"
        "COPY public.tips_auth_local_users (user_id, password) FROM stdin;\n"
        "x\tdo-not-read\n"
        "\\.\n"
    )
    t = parse_copy_text(text)
    assert set(t) == {"tips_role"}  # unlisted table dropped entirely
    assert t["tips_role"] == [
        {"id": "1", "name": "A\tB", "description": None},  # org_id dropped
        {"id": "2", "name": "line1\nline2", "description": "back\\slash AB"},
    ]


def test_format_copy_text_round_trips(tables):
    assert parse_copy_text(format_copy_text(tables)) == tables


def test_fixture_contains_only_allowed_tables_and_columns(tables):
    for table, rows in tables.items():
        assert table in ALLOWED_COLUMNS
        for row in rows:
            assert set(row) <= set(ALLOWED_COLUMNS[table])


def test_is_pgdump_magic():
    assert is_pgdump(b"PGDMP\x01\x0e\x00")
    assert not is_pgdump(b"<?xml version")


def test_find_pg_restore_env_points_to_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("PG_RESTORE", str(tmp_path / "nope"))
    with pytest.raises(PgRestoreNotFound):
        find_pg_restore()


# ---------------------------------------------------------------------------
# Rules-engine XML conversion
# ---------------------------------------------------------------------------

def _attr(attr_id, value, op="EQUALS", disp=None):
    disp = value if disp is None else disp
    return (f'<Attribute Operator="{op}" DataType="String" AttributeId="{attr_id}" '
            f'AttributeValue="{value}" AttributeValueDispName="{disp}"></Attribute>')


def test_service_match_drops_implicit_protocol_and_keeps_and():
    xml = ('<Rule RuleId="r"><Condition><Expression Operator="and">'
           '<Expression Operator="and">' + _attr("Radius:IETF:NAS-Port-Type", "15", disp="Ethernet (15)")
           + _attr("Authorization:[Endpoints Repository]:Category", "Printer") + '</Expression>'
           + _attr("Connection:Protocol", "RADIUS") + '</Expression></Condition></Rule>')
    warnings: list[str] = []
    expr = service_match(xml, warnings, "svc")
    assert warnings == []
    assert expr["operator"] == "and" and expr["displayOperator"] == "MATCHES_ALL"
    assert [(a["type"], a["name"], a["displayValue"]) for a in expr["attributes"]] == [
        ("Radius:IETF", "NAS-Port-Type", "Ethernet (15)"),
        ("Authorization:[Endpoints Repository]", "Category", "Printer"),
    ]


def test_service_match_missing_operator_is_match_any():
    xml = ('<Rule><Condition><Expression Operator="and"><Expression>' + _attr("Device:Device Type", "aruba")
           + '</Expression>' + _attr("Connection:Protocol", "RADIUS") + '</Expression></Condition></Rule>')
    expr = service_match(xml, [], "svc")
    assert expr["operator"] == "OR" and expr["displayOperator"] == "MATCHES_ANY"


def test_service_match_protocol_only_is_match_all():
    xml = '<Rule><Condition><Expression>' + _attr("Connection:Protocol", "RADIUS") + '</Expression></Condition></Rule>'
    assert service_match(xml, [], "svc") is None


def test_multi_predicate_without_operator_warns():
    xml = ('<Policy RuleCombiningAlgId="first-applicable"><Rule><Condition><Expression>'
           + _attr("Tips:Role", "a") + _attr("Tips:Role", "b") + '</Expression></Condition>'
           '<Result AttributeId="Tips:Role" AttributeValue="9" AttributeValueDispName="x"></Result></Rule></Policy>')
    warnings: list[str] = []
    policy_rules(xml, warnings, "Role Mapping Policy 'p'")
    assert len(warnings) == 1 and "no AND/OR operator" in warnings[0]


def test_policy_results_resolve_ids_with_display_fallback():
    xml = ('<Policy RuleCombiningAlgId="evaluate-all">'
           '<Rule><Condition><Expression>' + _attr("Tips:Role", "a") + '</Expression></Condition>'
           '<Result AttributeId="Tips:Enforcement-Profile" AttributeValue="1,3002" AttributeValueDispName="stale"></Result></Rule>'
           '<Rule><Condition><Expression>' + _attr("Tips:Role", "b") + '</Expression></Condition>'
           '<Result AttributeId="Tips:Enforcement-Profile" AttributeValue="99" AttributeValueDispName="Kept"></Result></Rule>'
           '</Policy>')
    algo, rules = policy_rules(xml, [], "p", {"Tips:Enforcement-Profile": {"1": "[Allow]", "3002": "Mine"}})
    assert algo == "evaluate-all"
    assert [r["index"] for r in rules] == [0, 1]
    assert rules[0]["results"] == [{"name": "Enforcement-Profile", "type": "Tips", "value": "1,3002", "displayValue": "[Allow], Mine"}]
    assert rules[1]["results"][0]["displayValue"] == "Kept"


def test_malformed_rule_xml_warns_instead_of_failing():
    warnings: list[str] = []
    assert service_match("<Rule><Condition>", warnings, "Service 'x'") is None
    assert warnings and "could not be read" in warnings[0]


# ---------------------------------------------------------------------------
# Raw model from the lab DB
# ---------------------------------------------------------------------------

def test_services_in_true_precedence_order(raw):
    services = raw["services"]
    assert [s["precedence"] for s in services] == list(range(1, 29))
    assert services[0]["name"] == "[Policy Manager Admin Network Login Service]"
    assert services[0]["enabled"] == "false"
    dividers = {s["name"]: s["precedence"] for s in services if s["name"].startswith("---")}
    assert dividers == {"-----------WIRED--------------": 11, "-----------WIRELESS--------------": 15}


def test_xml_export_order_is_not_precedence(xml_ir, db_ir):
    """The export groups services by element type; only the DB knows the real order."""
    xml_order = [s.name for s in xml_ir.services.values()]
    db_order = [s.name for s in sorted(db_ir.services.values(), key=lambda s: s.precedence)]
    assert sorted(xml_order) == sorted(db_order)
    assert xml_order != db_order
    assert all(s.precedence is None for s in xml_ir.services.values())


def test_db_has_objects_the_export_leaves_out(db_ir, xml_ir):
    """The export only contains objects reachable from its services."""
    db_profiles = {p.name for p in db_ir.enforcement_profiles.values()}
    xml_profiles = {p.name for p in xml_ir.enforcement_profiles.values()}
    assert xml_profiles <= db_profiles
    # Only the two lab profiles still wired to nothing (plus ClearPass built-ins) are DB-only.
    assert {n for n in db_profiles - xml_profiles if not n.startswith("[")} == {
        "kit-lab-wired 802.1X Wired Default Profile", "test-generic-application-enforcment",
    }
    assert len(db_ir.roles) > len(xml_ir.roles)


def test_dur_profile_keeps_generated_radius_attributes(db_ir):
    p = _profile(db_ir, "test-dur-enforcement-profile")
    generated = [a.name for a in p.attributes if not a.type.startswith("DUR:")]
    assert generated[0] == "Aruba-CPPM-Role"
    assert "port-access role test-dur-role" in p.attributes[0].value


def test_dur_profile(db_ir):
    p = _profile(db_ir, "test-dur-enforcement-profile")
    assert p.product == "durPluginA"
    dur = {a.name: a.value for a in p.attributes if a.type == "DUR:durPluginA"}
    assert dur["roleName"] == "test-dur-role"
    assert dur["policy"] == "test-policy"
    # The generated Aruba-CPPM-Role RADIUS attribute comes first, by order_no.
    assert p.attributes[0].type == "Radius:Aruba"


def test_snmp_agent_and_application_profiles(db_ir):
    snmp = _profile(db_ir, "test-snmp-enforcement")
    assert snmp.profile_type == "snmp"
    assert {a.name: a.value for a in snmp.attributes} == {"SessionTimeout": "30", "VLAN": "30", "ResetConnection": "true"}
    agent = _profile(db_ir, "test-agent-enforcment")
    assert agent.profile_type == "agent"
    assert {a.name for a in agent.attributes} == {"BounceClient", "Message"}
    assert _profile(db_ir, "cli-based-enforcement").profile_type == "generic_accept"


def test_coa_template_names_match_export(db_ir, xml_ir):
    for name in ("[H3C - Terminate Session]", "[Cisco - Terminate Session]"):
        assert _profile(db_ir, name).template == _profile(xml_ir, name).template != ""


def test_literal_secret_attribute_values_are_masked(db_ir):
    mpsk = _profile(db_ir, "test-mpsk Aruba Wireless with MPSK Default Profile")
    secret = next(a for a in mpsk.attributes if a.name == "Aruba-MPSK-Passphrase")
    assert secret.value == secret.display_value == HIDDEN_VALUE
    # A template reference is not a secret and stays visible.
    ref = next(a for a in _profile(db_ir, "[Registered Device MPSK]").attributes if a.name == "Aruba-MPSK-Passphrase")
    assert ref.value.startswith("%{")


@pytest.mark.parametrize("name,expected", [
    ("Aruba-MPSK-Passphrase", True), ("Tunnel-Password", True), ("Cisco-Pre-Shared-Key", True),
    ("snmp-community", True), ("Aruba-User-Role", False), ("Keyboard-Layout", False),
])
def test_secret_attribute_name_rule(name, expected):
    masked = pgdump_parser._mask_secret({"name": name, "value": "literal", "displayValue": "literal"})
    assert (masked["value"] == HIDDEN_VALUE) is expected


def test_no_rule_conversion_warnings(db_ir):
    assert db_ir.warnings == []
    assert db_ir.source_format == "pgdump"


# ---------------------------------------------------------------------------
# Parity: same lab, two inputs, same diagrams
# ---------------------------------------------------------------------------

# Profile attributes the XML export blanks but the DB keeps (as a reference or masked).
_EXPORT_BLANKED_ATTRIBUTES = {"Aruba-MPSK-Passphrase"}


def _export_comparable(attrs):
    """Known difference: for a Downloadable User Role profile the export carries
    only the DUR settings, while the DB also stores the RADIUS attributes
    ClearPass generates from them (Aruba-CPPM-Role with the compiled role CLI,
    Session-Timeout, ...)."""
    if any(a["type"].startswith("DUR:") for a in attrs):
        attrs = [a for a in attrs if a["type"].startswith("DUR:")]
    return [(a["name"], a["type"], a["display_value"]) for a in attrs if a["name"] not in _EXPORT_BLANKED_ATTRIBUTES]


def _flow(svc, ir):
    return dataclasses.asdict(compile_service(svc, ir))


def _service_names():
    return [s["name"] for s in parse(XML_FIXTURE)["services"]]


@pytest.mark.parametrize("name", _service_names())
def test_parity_flow_graph(name, xml_ir, db_ir):
    xs, ds = _svc(xml_ir, name), _svc(db_ir, name)
    assert xs.id == ds.id  # stable IDs: service selection works across inputs
    assert _flow(xs, xml_ir) == _flow(ds, db_ir)


def _profile_view(p):
    return (p["name"], p["profile_type"], p["action"], p["template"], p["tacacs_services"],
            p["product"], p["nad_groups"], _export_comparable(p["attributes"]))


@pytest.mark.parametrize("name", _service_names())
def test_parity_details(name, xml_ir, db_ir):
    xd = build_clearpass_details(_svc(xml_ir, name), xml_ir)
    dd = build_clearpass_details(_svc(db_ir, name), db_ir)
    xc, dc = dict(xd["service_context"]), dict(dd["service_context"])
    # Known differences: "Other settings" exist only in the export; precedence only in the DB.
    xc.pop("extras"), dc.pop("extras")
    assert xc.pop("precedence") is None
    assert dc.pop("precedence") == _svc(db_ir, name).precedence is not None
    assert xc == dc
    for kind in ("role_mapping_rules", "enforcement_rules"):
        assert len(xd[kind]) == len(dd[kind])
        for xr, dr in zip(xd[kind], dd[kind]):
            for key in ("rule_id", "condition_text", "action_text", "on_match", "linked_names"):
                assert xr[key] == dr[key], (kind, xr["index"], key)
            assert [_profile_view(p) for p in xr["profiles"]] == [_profile_view(p) for p in dr["profiles"]]


# ---------------------------------------------------------------------------
# API (pg_restore replaced by the committed fixture)
# ---------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture()
def fake_restore(monkeypatch, tables):
    monkeypatch.setattr(pgdump_parser, "read_pgdump", lambda path: tables)


def _upload(path, data, name="lab.pgdump"):
    return client.post(path, files={"file": (name, io.BytesIO(data), "application/octet-stream")})


def test_api_services_from_pgdump(fake_restore):
    res = _upload("/api/services", b"PGDMP-fake-archive")
    assert res.status_code == 200
    services = res.json()["services"]
    assert [s["precedence"] for s in services] == list(range(1, 29))
    assert sum(s["is_category"] for s in services) == 2


def test_api_flow_from_pgdump_matches_xml(fake_restore, xml_ir):
    svc = _svc(xml_ir, "test-mpsk Aruba Wireless with MPSK")
    db = _upload(f"/api/flow?service={svc.id}", b"PGDMP-fake-archive").json()
    xml = client.post(
        f"/api/flow?service={svc.id}",
        files={"file": ("lab.xml", io.BytesIO(XML_FIXTURE.read_bytes()), "application/xml")},
    ).json()
    assert db["nodes"] == xml["nodes"] and db["edges"] == xml["edges"]


def test_api_pgdump_extension_without_magic_is_422():
    res = _upload("/api/services", b"not a dump")
    assert res.status_code == 422


def test_api_pgdump_missing_pg_restore_is_500(monkeypatch):
    def boom(path):
        raise PgRestoreNotFound("pg_restore not found")
    monkeypatch.setattr(pgdump_parser, "read_pgdump", boom)
    res = _upload("/api/services", b"PGDMP-fake-archive")
    assert res.status_code == 500
    assert "pg_restore" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Real backup (local only)
# ---------------------------------------------------------------------------

def _pg_restore_available():
    try:
        find_pg_restore()
        return True
    except PgRestoreNotFound:
        return False


@pytest.mark.skipif(not REAL_DUMP.exists() or not _pg_restore_available(),
                    reason="needs the git-ignored lab backup and pg_restore")
def test_real_dump_reads_same_structure_as_fixture(raw):
    real = pgdump_parser.parse_pgdump(REAL_DUMP)
    assert [s["precedence"] for s in real["services"]] == [s["precedence"] for s in raw["services"]]
    assert len(real["radiusEnfProfiles"]) == len(raw["radiusEnfProfiles"])
    assert real["warnings"] == []
