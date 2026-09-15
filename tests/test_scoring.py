"""Backlink Ops — scoring tests.

These lock the numbers the associates are measured on. If a change here is
intentional, update the expected values AND add a line to docs/FEATURE_LOG.md
saying the ladder moved — associates must never find their target changed
silently.

Run:  python -m pytest tests/test_scoring.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.backlink_ops.scoring import day_stats, host_of, score_entry  # noqa: E402


def entry(**kw):
    base = {"id": "e1", "url": "https://example.com/a", "type": "directory", "da": 25,
            "spam": 1, "follow": "dofollow", "anchor": "x", "target": "/y",
            "relevant": True, "indexed": False}
    base.update(kw)
    return base


def test_host_normalises_www():
    assert host_of("https://www.Example.COM/path") == "example.com"
    assert host_of("not a url") == "not a url"


def test_base_directory_link():
    # 3 base * 1.0 (DA 25) + 3 dofollow + 4 relevant = 10.0
    assert score_entry(entry(), [])["pts"] == 10.0


def test_guest_post_high_da():
    # 15 * 1.7 (DA 60) + 3 + 4 + 2 indexed = 34.5
    e = entry(type="guest_post", da=60, indexed=True)
    r = score_entry(e, [])
    assert r["pts"] == 34.5
    assert r["tier"] == "high"


def test_low_da_is_penalised():
    # 3 * 0.6 + 3 + 4 = 8.8
    assert score_entry(entry(da=10), [])["pts"] == 8.8


def test_spam_score_strips_value():
    # (3 * 1.0 + 3 + 4) * 0.35 = 3.5
    r = score_entry(entry(spam=9), [])
    assert r["pts"] == 3.5
    assert any("Spam score" in f for f in r["flags"])


def test_nofollow_loses_bonus_and_flags():
    r = score_entry(entry(follow="nofollow"), [])
    assert r["pts"] == 7.0
    assert any("Nofollow" in f for f in r["flags"])


def test_repeat_domain_decays():
    a = entry(id="a", url="https://same.com/1")
    b = entry(id="b", url="https://same.com/2")
    solo = score_entry(a, [a])["pts"]
    paired = score_entry(a, [a, b])["pts"]
    assert paired < solo
    assert paired == round(solo * 0.7, 1)


def test_rejected_entries_do_not_count():
    rows = [entry(id="a"), entry(id="b", url="https://other.com/1")]
    st = day_stats(rows, {"b": {"status": "rejected"}}, [], 1, "agenticai")
    assert st["counted"] == 1
    assert st["rejected"] == 1
    assert not next(r for r in st["reqs"] if r["k"] == "fix")["ok"]


def test_level_one_completion_gate():
    # v1.1 ladder: Level 1 is 250 points AND a floor of 40 links a day
    # (the team already does 30-40; the old 60-point day measured nothing).
    rows = [entry(id=f"e{i}", type="guest_post", da=45,
                  url=f"https://site{i}.com/p", anchor=f"anchor {i}") for i in range(40)]
    queries = [{"kw": "a"}, {"kw": "b"}, {"kw": "c"}]
    st = day_stats(rows, {}, queries, 1, "agenticai")
    assert st["points"] >= 250
    assert st["done"] is True
    assert st["band"] == "great"


def test_level_one_links_floor_is_enforced():
    # 39 strong links clear the points target but not the 40-link floor.
    rows = [entry(id=f"e{i}", type="guest_post", da=45,
                  url=f"https://site{i}.com/p", anchor=f"anchor {i}") for i in range(39)]
    st = day_stats(rows, {}, [{"kw": "a"}] * 3, 1, "agenticai")
    assert st["points"] >= 250
    assert st["done"] is False
    links = next(r for r in st["reqs"] if r["k"] == "links")
    assert links["ok"] is False and links["now"] == "39 / 40"


def test_level_targets_can_be_overridden_from_config():
    # The superuser edits targets on the desk; they land in bo_config['levels'].
    rows = [entry(id=f"e{i}", type="directory", da=25, url=f"https://d{i}.com/p",
                  anchor=f"a {i}") for i in range(10)]
    cfg = {"level": 1, "levels": {"1": {"target": 50, "min_links": 10}}}
    st = day_stats(rows, {}, [{"kw": "a"}] * 3, 1, "agenticai", cfg=cfg)
    assert st["level"]["target"] == 50 and st["level"]["min_links"] == 10
    assert st["done"] is True
    # Out-of-range and non-numeric overrides are ignored, never crash.
    bad = {"level": 1, "levels": {"1": {"target": "lots", "min_links": -5}}}
    st2 = day_stats(rows, {}, [], 1, "agenticai", cfg=bad)
    assert st2["level"]["target"] == 250 and st2["level"]["min_links"] == 0


def test_level_three_demands_more():
    rows = [entry(id=f"e{i}", type="directory", da=25, url=f"https://d{i}.com/p") for i in range(8)]
    st = day_stats(rows, {}, [{"kw": "a"}] * 5, 3, "agenticai")
    assert st["done"] is False
    assert not next(r for r in st["reqs"] if r["k"] == "high")["ok"]


def test_exact_match_anchor_ratio_flags():
    rows = [entry(id=f"e{i}", url=f"https://d{i}.com/p",
                  anchor="whatsapp automation for hospitals") for i in range(3)]
    st = day_stats(rows, {}, [], 1, "agenticai")
    assert not next(r for r in st["reqs"] if r["k"] == "anchor")["ok"]
