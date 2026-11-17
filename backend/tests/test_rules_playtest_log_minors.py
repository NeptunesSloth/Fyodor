"""Break-it playtest, log lines. M6: Wheel of Fortune ("Each player discards their hand, then draws seven cards") logged "Alice discarded …
from Bob's hand"; a player discards from their own hand (701.9a): "Bob discarded …". M7: every attack logged "… recorded for Elvish
Mystic — Engaged110j: 4", the rules engine's own bookkeeping; it is neither logged nor shown on the card now.
Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [real("Wheel of Fortune", "{2}{R}", 3, "Sorcery", "Each player discards their hand, then draws seven cards.", None, "R"),
         real("Delirium Skeins", "{2}{B}", 3, "Sorcery", "Each player discards three cards.", None, "B"),
         real("Windfall", "{2}{U}", 3, "Sorcery", "Each player discards their hand, then draws cards equal to the greatest number of cards a "
              "player discarded this way.", None, "U"),
         real("Mind Rot", "{2}{B}", 3, "Sorcery", "Target player discards two cards.", None, "B")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _line(entry) -> str:
    return "".join(p.t or p.name or "".join(g.name or "" for g in (p.group or [])) for p in entry.parts)


def test_each_player_discards_their_own_hand_in_the_log(cards):
    s = build(cards, ["Wheel of Fortune", "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears"])
    to_phase(s, "main1", turn=3)
    to_hand(s, "Grizzly Bears", "p2")
    to_hand(s, "Llanowar Elves", "p2")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Wheel of Fortune")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wheel of Fortune").id)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    lines = [_line(e) for e in s.state.log]
    discards = [x for x in lines if " discarded " in x]
    assert any(x.startswith("Bob discarded ") and "Llanowar Elves" in x for x in discards), discards
    assert any(x.startswith("Alice discarded ") for x in discards), discards
    assert not any("from Bob's hand" in x for x in discards), discards
    assert card_named(s, "Llanowar Elves", "p2").zone == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("spell, targets", [("Delirium Skeins", []), ("Windfall", []), ("Mind Rot", ["p2"])])
def test_other_discard_effects_name_the_discarding_player(cards, spell, targets):
    """(second pass S2: Kolaghan's Command's "target player discards a card", Delirium Skeins, Windfall)"""
    s = build(cards, [spell, "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears", "Wrath of God"])
    to_phase(s, "main1", turn=3)
    for name in ("Grizzly Bears", "Llanowar Elves", "Wrath of God"):
        to_hand(s, name, "p2")
    to_hand(s, "Grizzly Bears")
    to_hand(s, spell)
    mana(s, B=1, U=1, C=2)
    seen = len(s.state.log)
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id, targets=targets)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    discards = [x for x in (_line(e) for e in s.state.log[seen:]) if " discarded " in x]
    assert any(x.startswith("Bob discarded ") for x in discards), discards
    assert not any("from Bob's hand" in x for x in discards), discards
    check(s)


def test_the_engines_attack_bookkeeping_is_not_logged_or_shown(cards):
    from app.rules.wave110j_cards import ENGAGED

    s = build(cards, ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert ENGAGED in s.state.cards[bear.id].choices  # (still kept: "since your last upkeep", Wiitigo)
    assert not any(ENGAGED in _line(e) for e in s.state.log)
    assert ENGAGED not in (s.view("p1")["cards"][bear.id].get("choices") or {})
    check(s)
