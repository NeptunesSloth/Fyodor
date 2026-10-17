"""Wave 49A: single-wording gaps of cards ranked 9,000 and up (CR 2026-09-25), real Oracle text (tests/fixtures/wave49a_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 601.2f, 118.7a-c: "This spell costs {2}{U} less to cast if you've cast an instant or sorcery spell this turn." (Stormwing Entity), "… {U}{U}{U} less … if an
  opponent has drawn four or more cards this turn" (Even the Score), "During your turn, this spell costs {2}{U}{U} less to cast." (Discontinuity), "… {1}{U} less to
  cast if it targets an instant or sorcery spell." (Brush Off) - a generic amount and a colored one come off the total cost together; the condition is read as the total cost is
  determined, so a spell that misses it costs its full price.
* 608.2h: "Exile target creature. If it had mana value 3 or less, surveil 2." (Consuming Ashes) - the creature as it last existed on the battlefield.
* 201.4: "Exile target nonwhite attacking creature. You gain life equal to its toughness." on the card named Exile - the verb at the start of the sentence is not the card's name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave43b_kit import on_top

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49a_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49a", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Stormwing Entity", "Even the Score", "Discontinuity", "Brush Off", "Consuming Ashes", "Exile", "Barren Glory", "Destroy the Evidence", "Regenerate"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)


def asked(s, limit=20):
    """Pass priority until a decision is asked (returned), or the stack is empty (None)."""
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_stormwing_entity_costs_two_blue_less_after_an_instant(cards):
    s = build(cards, ["Stormwing Entity", "Shock"])
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):  # {3}{U}{U} with no instant or sorcery cast yet
        cast(s, "Stormwing Entity")
    mana(s, R=1)
    cast(s, "Shock", targets=["p2"])
    settle(s)
    assert life(s, "p2") == 38
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stormwing Entity").id)  # {1}{U}: the pool's U and C
    settle(s)
    assert s.state.cards[card_named(s, "Stormwing Entity").id].zone == "p1:battlefield"
    check(s)


def test_even_the_score_costs_no_blue_once_an_opponent_drew_four(cards):
    s = build(cards, ["Even the Score"])
    mana(s, C=2)
    with pytest.raises(ActionError):  # {2}{U}{U}{U} for X=2: Bob has drawn nothing this turn
        cast(s, "Even the Score", x_value=2)
    act(s, "p2", type="draw", count=3)
    with pytest.raises(ActionError):  # three cards are not four
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Even the Score").id, x_value=2)
    act(s, "p2", type="draw", count=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Even the Score").id, x_value=2)  # {2}: both pool mana
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2
    check(s)


def test_discontinuity_costs_less_only_during_your_turn(cards):
    s = build(cards, ["Discontinuity"])
    stops(s)
    mana(s, U=1, C=1)
    discontinuity = to_hand(s, "Discontinuity")
    to_phase(s, "upkeep", turn=2)  # Bob's turn
    act(s, "p2", type="pass_priority")
    with pytest.raises(ActionError):  # {3}{U}{U}{U} on Bob's turn
        act(s, "p1", type="cast_spell", card_id=discontinuity.id)
    check(s)


def test_discontinuity_costs_two_blue_and_two_less_on_your_turn(cards):
    s = build(cards, ["Discontinuity"])
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Discontinuity").id)  # {1}{U}
    assert s.state.cards[card_named(s, "Discontinuity").id].zone == "p1:exile"  # it ended the turn, exiling itself from the stack
    check(s)


def bob_casts(s, name, **kw):
    """Alice passes in her main phase (every player gets priority, stops on); Bob casts this card at instant speed."""
    act(s, "p1", type="pass_priority")
    mana(s, "p2", U=2, R=1, C=3)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, name, "p2").id, **kw)
    return card_named(s, name, "p2")


def test_brush_off_costs_less_when_it_targets_an_instant_or_sorcery(cards):
    s = build(cards, ["Brush Off"], ["Shock"])
    stops(s)
    shock = bob_casts(s, "Shock", targets=["p1"])
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Brush Off").id, targets=[shock.id])  # {1}{U}: it targets an instant
    settle(s)
    assert s.state.cards[shock.id].zone == "p2:graveyard" and life(s) == 40  # countered
    check(s)


def test_brush_off_costs_full_price_against_a_creature_spell(cards):
    s = build(cards, ["Brush Off"], ["Thought Sponge"])
    stops(s)
    sponge = bob_casts(s, "Thought Sponge")
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):  # {2}{U}{U}: a creature spell is no instant or sorcery
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Brush Off").id, targets=[sponge.id])
    mana(s, U=1, C=1)  # ... {2}{U}{U} is four mana
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Brush Off").id, targets=[sponge.id])
    settle(s)
    assert s.state.cards[sponge.id].zone == "p2:graveyard"
    check(s)


def test_consuming_ashes_surveils_for_a_cheap_creature(cards):
    s = build(cards, ["Consuming Ashes"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, B=2, C=2)
    cast(s, "Consuming Ashes", targets=[bears.id])
    d = asked(s)
    assert d is not None and d.player == "p1" and s.state.cards[bears.id].zone == "p2:exile"  # mana value 2: surveil 2
    settle(s)
    check(s)


def test_consuming_ashes_does_not_surveil_for_an_expensive_creature(cards):
    s = build(cards, ["Consuming Ashes"], ["Stormwing Entity"])
    entity = put(s, "Stormwing Entity", "p2")
    mana(s, B=2, C=2)
    cast(s, "Consuming Ashes", targets=[entity.id])
    assert asked(s) is None and s.state.cards[entity.id].zone == "p2:exile"  # mana value 5
    check(s)


def test_exile_exiles_a_nonwhite_attacker_and_gains_its_toughness(cards):
    s = build(cards, ["Exile"], ["Grizzly Bears"])
    stops(s)
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Exile")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):  # Bears are not attacking yet
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Exile").id, targets=[bears.id])
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    act(s, "p2", type="pass_priority")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Exile").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:exile" and life(s, "p1") == 42
    check(s)


def test_destroy_the_evidence_reads_destroy_as_the_verb_not_its_name(cards):
    """"Destroy target land. Its controller reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard." - the
    card is named for its first word, which is the verb here (and so is the card Regenerate's)."""
    s = build(cards, ["Destroy the Evidence"], ["Grizzly Bears"])
    island = put(s, "Island", "p2")
    bears = on_top(s, "Grizzly Bears", "p2")
    mana(s, B=1, C=4)
    cast(s, "Destroy the Evidence", targets=[island.id])
    settle(s)
    assert s.state.cards[island.id].zone == "p2:graveyard" and s.state.cards[bears.id].zone == "p2:graveyard"  # Bears, then the next land (an Island)
    assert len(s.state.zones["p2:graveyard"]) == 3
    check(s)


@pytest.mark.parametrize("extra", ["", "hand", "permanent"])
def test_barren_glory_wins_only_with_an_empty_hand_and_no_other_permanents(cards, extra):
    """"If you control no permanents other than this enchantment and have no cards in hand, you win the game." is checked as her upkeep begins."""
    s = build(cards, ["Barren Glory"])
    put(s, "Barren Glory")
    assert not s.state.zones.get("p1:hand")  # (the table starts with empty hands)
    if extra == "hand":
        to_hand(s, "Forest")
    if extra == "permanent":
        put(s, "Forest")
    stops(s)
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert (s.state.rules.winner == "p1") == (extra == "")
    check(s)
