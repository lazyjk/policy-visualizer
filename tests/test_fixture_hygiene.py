"""Guards for committed lab fixtures and the sanitizer tool.

The replacement map itself is git-ignored (it lists the values it removes),
so these tests only use the map-independent checks plus synthetic maps.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

_spec = importlib.util.spec_from_file_location("sanitize_fixture", ROOT / "tools" / "sanitize_fixture.py")
sanitize_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sanitize_fixture)

LAB_FIXTURES = [FIXTURES / "LabKitchenSink.xml", FIXTURES / "pgdump" / "LabKitchenSink.copy.txt"]


@pytest.mark.parametrize("path", LAB_FIXTURES, ids=lambda p: p.name)
def test_lab_fixture_has_only_documentation_ips(path):
    """Real lab IPs must be mapped to RFC 5737 ranges before committing."""
    assert sanitize_fixture.leftovers(path.read_text(encoding="utf-8"), []) == []


def test_sanitize_applies_pairs_in_order():
    pairs = [("alice@corp.test", "svc@example.local"), ("corp.test", "example.local")]
    assert sanitize_fixture.sanitize("alice@corp.test dc.corp.test", pairs) == (
        "svc@example.local dc.example.local"
    )


def test_leftovers_never_echo_mapped_values():
    pairs = [("secret-domain.test", "example.local")]
    problems = sanitize_fixture.leftovers("host.secret-domain.test 10.1.2.3 192.0.2.5 127.0.0.1", pairs)
    assert problems == ["map entry #0 still present", "unlisted IPv4 10.1.2.3"]
    assert not any("secret-domain" in p for p in problems)


def test_load_map_rejects_malformed_entries(tmp_path):
    bad = tmp_path / "map.json"
    bad.write_text('[["only-one"]]', encoding="utf-8")
    with pytest.raises(ValueError):
        sanitize_fixture.load_map(bad)
