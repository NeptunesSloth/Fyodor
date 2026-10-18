"""Wave 50C: a modal mode that opens with "If" (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 608.2c / 700.2: Venser, Corpse Puppet's "• If you don't control a creature named The Hollow Sentinel, create The Hollow Sentinel …" is a mode like
  any other; its "if" is a condition of that mode, checked as the ability resolves (not an intervening "if" of the trigger, 603.4).
* 611.2a / 614.1: Rankle and Torbran's "• If a source would deal damage to a player or battle this turn, it deals that much damage plus 2 instead."
  is a replacement effect for the rest of the turn (ruling 2023-04-14: the additional 2 is dealt by the same source).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, attack, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
PROLIFERATE = card("Spread Contagion", set_code="w50c", number="P01", mana_cost="{G}", cmc=1.0, type_line="Sorcery", oracle_text="Proliferate.",
                   colors=["G"], color_identity=["G"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, PROLIFERATE], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def sentinels(s):
    return [c for c in s.state.cards.values() if c.name == "The Hollow Sentinel" and c.zone == "p1:battlefield"]


def proliferate(s):
    """Cast Spread Contagion (no permanent or player is chosen), then settle until Venser's trigger asks for its mode (or nothing is left)."""
    to_hand(s, "Spread Contagion")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Spread Contagion").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and "proliferate" in d.prompt.lower():
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        elif d is not None:
            return d
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return None
    raise AssertionError("never settled")


def test_venser_if_mode_makes_the_golem_only_while_none_is_there(cards):
    s = build(cards, ["Venser, Corpse Puppet", "Spread Contagion"], forests=30)
    put(s, "Venser, Corpse Puppet")
    d = proliferate(s)
    assert d is not None and d.prompt.startswith("Venser, Corpse Puppet: choose one")
    assert d.options[0].label.startswith("If you don't control a creature named The Hollow Sentinel")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0"])
    settle(s)
    assert len(sentinels(s)) == 1
    check(s)
    s = reloaded(s)
    assert len(sentinels(s)) == 1
    # a second time: the condition fails as the mode resolves, nothing more is made (the mode could still be chosen)
    s.state.cards[card_named(s, "Spread Contagion").id]  # (the spell is in the graveyard; another copy comes from the library)
    to_hand(s, "Spread Contagion")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Spread Contagion").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and "proliferate" in d.prompt.lower():
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
        elif d is not None:
            break
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "choose_cards"
    assert [o.id for o in d.options][0] == "0:0"  # (the "If" mode is offered while the Golem is there)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0"])
    settle(s)
    assert len(sentinels(s)) == 1
    check(s)


def rankle_hits_bob(cards, modes):
    """Rankle and Torbran (first strike, haste) attacks Bob and deals combat damage: the modes ``modes`` (option ids) are chosen; Alice then has Lightning Bolt."""
    s = build(cards, ["Rankle and Torbran", "Lightning Bolt"], forests=30)
    rt = put(s, "Rankle and Torbran")
    stops(s)
    attack(s, rt)
    d = ask(s)
    assert d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (0, 3)
    assert d.options[2].label.startswith("If a source would deal damage to a player or battle this turn")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=modes)
    settle(s)
    return s


def bolt_bob(s):
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    return before - life(s, "p2")


def test_rankle_and_torbran_damage_mode_adds_two_to_each_source_for_the_turn(cards):
    s = rankle_hits_bob(cards, ["2:0"])
    assert life(s, "p2") == 37  # (the combat damage was dealt before the mode was chosen)
    assert bolt_bob(s) == 5  # 3 + 2
    check(s)
    assert bolt_bob(reloaded(s)) == 5  # (the loaded table keeps the effect: the second Bolt is a second source, plus 2 again)


def test_rankle_and_torbran_without_the_damage_mode_deals_normal_damage(cards):
    s = rankle_hits_bob(cards, ["0:0"])
    assert len([c for c in s.state.cards.values() if c.name == "Treasure" and c.is_token]) == 2  # each player created one
    assert bolt_bob(s) == 3
    check(s)


def test_rankle_and_torbran_damage_mode_ends_with_the_turn(cards):
    s = rankle_hits_bob(cards, ["2:0"])
    to_phase(s, "main1", turn=3)
    assert bolt_bob(s) == 3
    check(s)
