"""Wave 51B: popular cards that were not FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave51b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* Arcane Denial: 603.7a delayed triggers at the beginning of the next turn's upkeep; "Its controller may draw up to two cards" is that player's choice, 0 to 2,
  made as the delayed trigger resolves (608.2d); "You draw a card" is the Denial's controller.
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
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer, on_top
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def test_the_cards_are_full(cards):
    for c in DATA:
        assert coverage.of_card_data(cards.resolve(c["name"])).level == "FULL", c["name"]


def to_choice(s, ids):
    """Pass priority (answering other decisions with their first options) until the choice with these option ids is asked."""
    until(s, lambda s: s.state.rules.decision is not None and [o.id for o in s.state.rules.decision.options] == ids, limit=300)
    return s.state.rules.decision


def denial(cards, draw):
    """Alice casts Lightning Bolt at Bob; Bob counters it with Arcane Denial; the next turn's upkeep is Bob's."""
    s = build(cards, ["Lightning Bolt"], ["Arcane Denial"])
    bolt, den = to_hand(s, "Lightning Bolt"), to_hand(s, "Arcane Denial", "p2")
    mana(s, "p1", R=1)
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=den.id, targets=[bolt.id])
    answer(s)
    assert zone_of(s, "Lightning Bolt").endswith("graveyard")
    s = reloaded(s)
    a, b = hand(s, "p1"), hand(s, "p2")
    d = to_choice(s, ["0", "1", "2"])
    assert d.player == "p1" and s.state.turn.number == 2 and s.state.turn.phase == "upkeep"  # the countered spell's controller chooses
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[str(draw)])
    answer(s)
    return s, a, b


@pytest.mark.parametrize("draw", [0, 2])
def test_arcane_denial_its_controller_draws_up_to_two_and_you_draw_one(cards, draw):
    s, a, b = denial(cards, draw)
    assert hand(s, "p1") == a + draw and hand(s, "p2") == b + 2  # (the Denial's draw, then Bob's own draw step)
    check(s)


def lore(s, name):
    return s.state.cards[card_named(s, name).id].counters.get("lore", 0)


def test_urzas_saga_grants_both_abilities_and_chapter_three_finds_only_a_zero_or_one_cost_artifact(cards):
    """714.2 chapters; 113.10 the Saga gains the abilities it names (a token's own quoted ability inside, 111.4); 202.1: "mana cost {0} or {1}" is the printed cost
    itself: Sol Ring ({1}) is found, Arcane Signet ({2}) and the lands are not."""
    s = build(cards, ["Urza's Saga", "Sol Ring", "Arcane Signet"])
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    saga = to_hand(s, "Urza's Saga")
    act(s, "p1", type="play_land", card_id=saga.id)
    answer(s)
    assert lore(s, "Urza's Saga") == 1
    assert any("{T}: Add {C}." in a.text for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[saga.id]).abilities)  # chapter I
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.stack, limit=300)
    answer(s)
    assert lore(s, "Urza's Saga") == 2
    mana(s, "p1", C=2)
    ab = next(a for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[saga.id]).abilities if a.text.startswith("{2}, {T}:"))
    act(s, "p1", type="activate_ability", card_id=saga.id, ability=ab.index)
    answer(s)
    construct = next(c for c in s.state.cards.values() if c.name == "Construct" and c.zone == "p1:battlefield")
    assert Plan(s.state, "p1", s.cards, None).ch(construct).pt == (1, 1)  # 0/0 +1/+1 for the one artifact: itself
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1" and s.state.rules.stack, limit=300)
    for name in ("Sol Ring", "Arcane Signet"):  # (drawn by now: back into the library before chapter III resolves)
        on_top(s, name, "p1")
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")
    d = s.state.rules.decision
    assert [o.label for o in d.options if o.card_id] == ["Sol Ring"]  # not Arcane Signet ({2}), not a land
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id)])
    answer(s)
    assert zone_of(s, "Sol Ring") == "p1:battlefield" and zone_of(s, "Urza's Saga") == "p1:graveyard"  # III, then sacrificed (714.4)
    check(s)


def mox(cards, hand, choose_card=None):
    """Alice casts Chrome Mox with ``hand`` besides it; the imprint is paid with ``choose_card`` (None: declined)."""
    s = build(cards, ["Chrome Mox", *hand])
    for name in hand:
        to_hand(s, name)
    c = to_hand(s, "Chrome Mox")
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "choose_one"  # asked with or without a legal card (101.4a)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if choose_card else "decline"])
    if choose_card:
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == choose_card)])
    answer(s)
    return s, c


@pytest.mark.parametrize(("card_name", "colors"), [("Lightning Bolt", {"R"}), ("Terminate", {"B", "R"})])
def test_chrome_mox_adds_one_mana_of_the_exiled_cards_colors(cards, card_name, colors):
    """Imprint (607.2a): the exiled card (face up, 406.3) is linked to the Mox; {T}: Add one mana of any of its colors (a multicolored one: a choice)."""
    s, c = mox(cards, ["Lightning Bolt", "Terminate", "Forest"], card_name)
    assert zone_of(s, card_name).endswith(":exile") and zone_of(s, "Forest").endswith(":hand")
    act(s, "p1", type="activate_ability", card_id=c.id, ability=1)
    d = s.state.rules.decision
    if len(colors) > 1:
        assert d is not None and sorted(o.label for o in d.options) == ["{B}", "{R}"]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert sum(s.state.players["p1"].mana.values()) == 1 and set(s.state.players["p1"].mana) <= colors
    check(s)


def veil(cards, bob_spell):
    """Alice casts Sol Ring; Bob answers with ``bob_spell`` at her Grizzly Bears; Alice answers that with Veil of Summer."""
    s = build(cards, ["Grizzly Bears", "Veil of Summer", "Sol Ring"], ["Terminate", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    spell, v, ring = to_hand(s, bob_spell, "p2"), to_hand(s, "Veil of Summer"), to_hand(s, "Sol Ring")
    mana(s, "p1", G=1, C=1)
    mana(s, "p2", B=1, R=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[bears.id])
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=v.id)
    return s, bears


def test_veil_of_summer_gives_you_and_your_permanents_hexproof_from_black_and_blue(cards):
    """702.11d, 702.11f: Terminate (black and red) can no longer target Alice's Bears or Alice; Alice draws (Bob cast a black spell this turn)."""
    s, bears = veil(cards, "Terminate")
    answer(s)  # (Alice's hand is empty but for what Veil draws)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"  # its target became illegal: Terminate did nothing
    assert len(s.state.zones["p1:hand"]) == 1  # Veil's own draw
    from app.rules import player_shields

    plan = Plan(s.state, "p1", s.cards, None)
    black, red = plan.ch(card_named(s, "Terminate", "p2")), plan.ch(card_named(s, "Lightning Bolt", "p2"))
    assert not player_shields.can_target(plan, "p2", "p1", black) and player_shields.can_target(plan, "p2", "p1", red)
    assert player_shields.can_target(plan, "p1", "p1", black)  # only what your opponents control (702.11d)
    check(s)


def test_veil_of_summer_does_not_stop_a_red_spell_or_draw_without_a_blue_or_black_one(cards):
    s, bears = veil(cards, "Lightning Bolt")
    answer(s)
    assert zone_of(s, "Grizzly Bears").endswith("graveyard") and not s.state.zones["p1:hand"]  # Bolt is red: no hexproof from red, no draw
    check(s)


def trawler(cards):
    """Alice's graveyard holds Sol Ring (1), Arcane Signet (2) and a second Scrap Trawler (3); the Trawler on the battlefield (3) dies to Bolt."""
    s = build(cards, ["Scrap Trawler", "Scrap Trawler", "Sol Ring", "Arcane Signet", "Lightning Bolt"])
    for name in ("Sol Ring", "Arcane Signet"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    first, second = [c for c in s.state.cards.values() if c.name == "Scrap Trawler" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "battlefield"})
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[first.id])
    return s, first


def test_scrap_trawler_returns_an_artifact_with_lesser_mana_value_than_the_one_that_left(cards):
    """Ruling 2017-02-09: the target has a lesser mana value than the artifact that caused the trigger, as it last existed on the battlefield (here the Trawler itself,
    3): Sol Ring and Arcane Signet qualify, the other Scrap Trawler (3) does not."""
    s, first = trawler(cards)
    for _ in range(8):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and sorted(o.label for o in d.options) == ["Arcane Signet", "Sol Ring"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Arcane Signet")])
    answer(s)
    assert zone_of(s, "Arcane Signet") == "p1:hand" and zone_of(s, "Sol Ring") == "p1:graveyard"
    check(s)


def test_chrome_mox_with_nothing_imprinted_adds_no_mana(cards):
    s, c = mox(cards, ["Lightning Bolt"], None)
    assert zone_of(s, "Lightning Bolt").endswith(":hand")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=c.id, ability=1)
    assert sum(s.state.players["p1"].mana.values()) == 0
    check(s)
