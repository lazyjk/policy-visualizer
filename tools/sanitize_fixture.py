#!/usr/bin/env python3
"""
Replace identifying lab values in a text fixture before it is committed.

The replacement map lives OUTSIDE the repo-tracked tree (default:
reference-files/sanitize_map.json, which is git-ignored), because the map
itself lists the values being removed. Format: a JSON list of
[old, new] pairs, applied in order — put longer, more specific strings
first (e.g. "user@corp.example" before "corp.example").

The same map is applied to the XML export and to the pgdump COPY-text
extract, so both fixtures stay consistent and the XML ↔ DB parity tests
keep matching.

Usage:
    python tools/sanitize_fixture.py FILE [FILE ...]           # rewrite in place
    python tools/sanitize_fixture.py --check FILE [FILE ...]   # report leftovers only
    python tools/sanitize_fixture.py --map other_map.json FILE

--check exits non-zero if any mapped value, or any IPv4 address outside the
allow-list below, is still present.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "reference-files" / "sanitize_map.json"

# IPv4 addresses that are safe to keep: loopback, unspecified, documentation
# ranges (RFC 5737) and the obvious dummy value used in lab rules.
_SAFE_IP = re.compile(r"^(127\.|0\.0\.0\.0$|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|1\.2\.3\.4$)")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def load_map(path: Path) -> list[tuple[str, str]]:
    pairs = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for item in pairs:
        if not (isinstance(item, list) and len(item) == 2 and all(isinstance(s, str) and s for s in item)):
            raise ValueError(f"bad map entry (expected [old, new]): {item!r}")
        out.append((item[0], item[1]))
    return out


def sanitize(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def leftovers(text: str, pairs: list[tuple[str, str]]) -> list[str]:
    """Problems still present in `text`. Mapped values are reported by their
    position in the map, never echoed, so --check output is safe to share."""
    found = [f"map entry #{i} still present" for i, (old, _) in enumerate(pairs) if old in text]
    found += sorted({f"unlisted IPv4 {ip}" for ip in _IPV4.findall(text) if not _SAFE_IP.match(ip)})
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--check", action="store_true", help="report leftovers, do not rewrite")
    args = ap.parse_args(argv)

    pairs = load_map(args.map)
    status = 0
    for f in args.files:
        # newline="" keeps the file's original line endings byte-for-byte.
        with f.open(encoding="utf-8", newline="") as fh:
            text = fh.read()
        if not args.check:
            new = sanitize(text, pairs)
            if new != text:
                with f.open("w", encoding="utf-8", newline="") as fh:
                    fh.write(new)
            text = new
        problems = leftovers(text, pairs)
        for p in problems:
            print(f"{f}: {p}")
        if problems:
            status = 1
        else:
            print(f"{f}: clean")
    return status


if __name__ == "__main__":
    sys.exit(main())
