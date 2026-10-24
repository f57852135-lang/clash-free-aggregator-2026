#!/usr/bin/env python3
"""Regression tests; run via `python tests/test_regression.py`."""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import aggregator as ag  # noqa: E402


def sample_yaml():
    return """proxies:
  - name: US - zhuhai.uk
    type: ss
    server: us1.example.com
    port: 8388
    cipher: aes-128-gcm
    password: pass1
  - name: JP - zhuhai.uk
    type: ss
    server: jp1.example.com
    port: 8388
    cipher: aes-128-gcm
    password: pass2
  - name: 1234567890
    type: trojan
    server: t1.example.com
    port: 443
    password: pass3
"""


def keep():
    return {"http", "socks5", "ss", "vmess", "vless", "trojan", "hysteria2", "tuic"}


def test_metadata_survives_valid_proxy():
    nodes = ag.parse_clash(sample_yaml(), "zhuhai")
    assert len(nodes) == 3
    valid = [n for n in nodes if ag.valid_proxy(n, keep())]
    assert len(valid) == 3
    assert all(n.get("_source") == "zhuhai" for n in valid)
    assert {n.get("_original_name") for n in valid} == {"US - zhuhai.uk", "JP - zhuhai.uk", "1234567890"}


def test_normalization_still_applies():
    nodes = ag.parse_clash(sample_yaml(), "zhuhai")
    assert ag.valid_proxy(nodes[2], keep())
    assert nodes[2]["type"] == "trojan"
    assert nodes[2]["password"] == "pass3"


def test_final_config_has_no_metadata_leak():
    nodes = ag.parse_clash(sample_yaml(), "zhuhai")
    nodes = [n for n in nodes if ag.valid_proxy(n, keep())]
    cfg = ag.build_config(nodes, {})
    assert len(cfg["proxies"]) == 3
    assert all(not any(k.startswith("_") for k in p) for p in cfg["proxies"])
    names = [p["name"] for p in cfg["proxies"]]
    assert any(n.startswith("US | zhuhai |") for n in names)
    assert any(n.startswith("JP | zhuhai |") for n in names)
    assert any(n.startswith("OT | zhuhai |") for n in names)


def test_region_filters_match_named_nodes():
    nodes = ag.parse_clash(sample_yaml(), "zhuhai")
    nodes = [n for n in nodes if ag.valid_proxy(n, keep())]
    cfg = ag.build_config(nodes, {})
    groups = {g["name"]: g for g in cfg["proxy-groups"]}
    names = [p["name"] for p in cfg["proxies"]]
    assert sum(bool(re.search(groups["United States Auto"]["filter"], n)) for n in names) == 1
    assert sum(bool(re.search(groups["Japan Auto"]["filter"], n)) for n in names) == 1


def test_select_diverse_round_robin():
    nodes = ([{"_source": "big", "i": i} for i in range(60)] +
             [{"_source": "mid", "i": i} for i in range(30)] +
             [{"_source": "small", "i": i} for i in range(10)])
    selected = ag.select_diverse(nodes, 20)
    counts = {s: sum(n["_source"] == s for n in selected) for s in ("big", "mid", "small")}
    assert counts == {"big": 7, "mid": 7, "small": 6}, counts
    assert len(ag.select_diverse(nodes, 100)) == 100
    assert len(ag.select_diverse(nodes, 300)) == 100


def test_region_stats_names_and_metadata_consistent():
    nodes = ag.parse_clash(sample_yaml(), "zhuhai")
    nodes = [n for n in nodes if ag.valid_proxy(n, keep())]
    tally = {}
    for n in nodes:
        region = ag.region_of(n.get("_original_name", ""))
        tally[region] = tally.get(region, 0) + 1
    assert tally == {"United States": 1, "Japan": 1, "Other": 1}, tally


def test_uk_filter_ignores_domain_suffix_and_keeps_real_labels():
    sample = """proxies:
  - name: FR - zhuhai.uk
    type: ss
    server: fr1.example.com
    port: 8388
    cipher: aes-128-gcm
    password: p1
  - name: UK - Node 01
    type: ss
    server: uk1.example.com
    port: 8388
    cipher: aes-128-gcm
    password: p2
  - name: London - Cloudflare
    type: ss
    server: lon1.example.com
    port: 8388
    cipher: aes-128-gcm
    password: p3
  - name: United Kingdom 02
    type: ss
    server: uk2.example.com
    port: 8388
    cipher: aes-128-gcm
    password: p4
"""
    nodes = ag.parse_clash(sample, "zhuhai")
    nodes = [n for n in nodes if ag.valid_proxy(n, keep())]
    cfg = ag.build_config(nodes, {})
    groups = {g["name"]: g for g in cfg["proxy-groups"]}
    uk_filter = groups["United Kingdom Auto"]["filter"]
    assert "(?<" not in uk_filter and "(?!" not in uk_filter, uk_filter
    pattern = re.compile(uk_filter)
    names = [p["name"] for p in cfg["proxies"]]
    french = next(n for n in names if n.endswith("FR - zhuhai.uk"))
    assert french.startswith("FR | zhuhai |"), french
    assert not pattern.search(french), f"false UK match: {french}"
    for suffix in ("UK - Node 01", "London - Cloudflare", "United Kingdom 02"):
        name = next(n for n in names if n.endswith(suffix))
        assert pattern.search(name), name
    assert len([n for n in names if pattern.search(n)]) == 3


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
        except Exception as exc:  # report all failures, including unexpected ones
            failed += 1
            print(f"[FAIL] {test.__name__}: {exc!r}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
