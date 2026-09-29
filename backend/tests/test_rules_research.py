"""Development-time rules research tooling (no network: synthetic rules texts)."""

from __future__ import annotations

import json

from tools.rules_research import cr, diff, update
from tools.rules_research.search import Index

OLD = """Magic: The Gathering Comprehensive Rules

These rules are effective as of April 4, 2026.

Contents

1. Game Concepts
7. Additional Rules
Glossary
Credits

1. Game Concepts

106. Mana

106.1. Mana is the primary resource in the game.

106.1a There are five colors of mana.

7. Additional Rules

702. Keyword Abilities

702.2. Deathtouch

702.2a Deathtouch is a static ability.

702.2b A creature with toughness greater than 0 that's been dealt damage by a source with deathtouch is destroyed.

Example: A 1/1 with deathtouch blocks a 5/5.

704. State-Based Actions

704.5a If a player has 0 or less life, that player loses the game.

Glossary

Deathtouch
A keyword ability that causes damage dealt by an object to be especially effective. See rule 702.2, "Deathtouch."

Credits

Magic: The Gathering Original Game Design: Richard Garfield
"""

NEW = OLD.replace("April 4, 2026", "September 25, 2026").replace(
    "704.5a If a player has 0 or less life, that player loses the game.",
    "704.5a If a player has 0 or less life, that player loses the game.\n\n704.5b If a player attempted to draw from an empty library, that player loses the game.",
).replace("106.1a There are five colors of mana.", "106.1a There are five colors of mana: white, blue, black, red, and green.").replace(
    "704. State-Based Actions",
    "702.300. Frobnicate\n\n702.300a Frobnicate is a triggered ability.\n\n704. State-Based Actions",
)


def test_parse_rules_examples_and_glossary():
    rules = cr.parse(OLD)
    assert str(rules.effective) == "2026-04-04"
    assert rules.sections == {"1": "Game Concepts", "7": "Additional Rules"}
    assert rules.rules["702.2b"].examples == ["Example: A 1/1 with deathtouch blocks a 5/5."]
    assert rules.title("702.2b") == "Deathtouch" and rules.title("704.5a") == "State-Based Actions"
    assert rules.rules["702.2a"].parent == "702.2" and rules.rules["702.2"].parent == "702"
    assert "Deathtouch" in rules.glossary and "Credits" not in rules.glossary


def test_diff_classifies_changes_and_points_at_engine_components():
    d = diff.compare(cr.parse(OLD), cr.parse(NEW))
    kinds = {(c.kind, c.number) for c in d.changes}
    assert ("MODIFIED RULE", "106.1a") in kinds and ("NEW RULE", "704.5b") in kinds
    assert ("NEW KEYWORD", "702.300") in kinds
    assert next(c for c in d.changes if c.number == "704.5b").category == "STATE-BASED ACTION CHANGE"
    affected = d.affected_components()
    assert "app/rules/sba.py" in affected and "app/rules/mana.py" in affected
    md = diff.markdown(d, card_counts={"frobnicate": 12})
    assert "Rules update impact" in md and "+There are five colors of mana: white" in md
    assert "2026-04-04 → 2026-09-25" in md
    assert diff.markdown(diff.compare(cr.parse(OLD), cr.parse(OLD))).endswith("No rule text changed.\n")


def test_search_by_words_and_by_number():
    index = Index(cr.parse(OLD))
    hits = index.search("damage deathtouch source destroyed")
    assert hits[0][1] == "702.2b"
    assert [h[1] for h in index.search("702.2")] == ["702.2", "702.2a", "702.2b"]
    assert any(h[1] == "Glossary: Deathtouch" for h in index.search("deathtouch"))


def test_ingest_stores_versions_and_writes_the_change_report(tmp_path):
    root, reports = tmp_path / "cr", tmp_path / "reports"
    first = update.ingest(OLD, source_url="file:old.txt", root=root, reports=reports, min_rules=1)
    assert first["status"] == "stored" and not (reports / "rules_changes.md").exists()
    assert update.ingest(OLD, source_url="file:old.txt", root=root, reports=reports, min_rules=1)["status"] == "unchanged"
    second = update.ingest(NEW, source_url="file:new.txt", root=root, reports=reports, min_rules=1)
    assert second["changes"] == 4  # 106.1a, 704.5b, 702.300, 702.300a and "app/rules/sba.py" in second["affected"]
    meta = json.loads((root / "2026-09-25" / "source.json").read_text())
    assert meta["previous"] == "2026-04-04" and len(meta["sha256"]) == 64
    assert (root / "2026-09-25" / "sha256.txt").read_text().startswith(meta["sha256"])
    assert "704.5b" in (reports / "rules_changes.md").read_text()


def test_link_discovery():
    page = '<a href="https://media.wizards.com/2026/downloads/MagicCompRules 20260925.txt">TXT</a>' \
           '<a href="https://media.wizards.com/2026/downloads/MagicCompRules 20260925.pdf">PDF</a>'
    assert update.find_txt_link(page).endswith("20260925.txt")
    news = '<a href="/en/news/announcements/some-set-update-bulletin">x</a><a href="/en/news/feature/some-set-release-notes">'
    found = update.discover_bulletins({"p": news})
    assert sorted(b["kind"] for b in found) == ["release_notes", "update_bulletin"]


def test_every_state_based_action_in_the_stored_rules_is_reviewed():
    from tools.rules_research import audit
    from tools.rules_research.store import latest_text

    text = latest_text()
    if text is None:  # a checkout without researched rules
        return
    rows = audit.audit(cr.parse(text))
    problems = [(num, status) for num, status, _, _ in rows if status in ("UNREVIEWED", "STALE")]
    assert problems == [], "review these state-based actions against the engine (tools/rules_research/audit.py)"
    assert {num for num, *_ in rows} >= {"704.5a", "704.6c", "704.6d"}
