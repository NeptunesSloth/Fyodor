"""-- public reveals -- the reveal notice's words are the rules engine's: a client's own "reveal the top card" can't carry a source, an
"until" or a "found" (they would put any text a client likes into everyone's log and notice), while the engine's reveals name the spell
or ability that reveals (a clash: Research the Deep). Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import json

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, to_hand

EXTRA = [
    real("Research the Deep", "{1}{U}", 2, "Sorcery",
         "Draw a card. Clash with an opponent. If you win, return Research the Deep to its owner's hand.", None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _reveals(s):
    return [e for e in s.state.log if e.reveal is not None]


def test_a_client_reveal_carries_no_source_until_or_found(cards):
    s = build(cards)
    act(s, "p1", type="reveal_top", count=2, source="Bob concedes <b>now</b>", until=True, found=True)
    (entry,) = _reveals(s)
    assert entry.reveal.source is None and not entry.reveal.until and not entry.reveal.found
    for viewer in ("p1", "p2"):
        seen = json.dumps(s.view(viewer)["log"])
        assert "Bob concedes" not in seen and " found " not in seen and "none found" not in seen
    recorded = s.history.actions[-1]
    assert recorded.type == "reveal_top" and recorded.source is None and not recorded.until and not recorded.found  # (what replays)
    check(s)


def test_a_clash_names_the_spell_that_reveals(cards):
    s = build(cards, ["Research the Deep"])
    spell = to_hand(s, "Research the Deep")
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    found = _reveals(s)
    assert {e.reveal.player for e in found} == {"p1", "p2"}  # (each clashing player reveals their top card, 701.30c)
    assert all(e.reveal.source == "Research the Deep" for e in found)
    assert "(Research the Deep)" in json.dumps(s.view("p2")["log"])
    check(s)
