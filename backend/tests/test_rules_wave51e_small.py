"""Wave 51E: small pieces of commanders' text (CR 2026-09-25), real Oracle text (tests/fixtures/wave51e_small_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.2c / 601.2h: Satoru, the Infiltrator - "if none of them were cast or no mana was spent to cast them": every permanent of the aggregated enter was put
  there without being cast, or cast with no mana spent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attack, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave43b_kit import on_top

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51e_small_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51s", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SATORU = "Satoru, the Infiltrator"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s):
    return len(s.state.zones["p1:hand"])


def test_satoru_draws_when_a_creature_enters_without_being_cast(cards):
    s = build(cards, [SATORU, "Young Wolf", "Dose of Dawnglow"], [])
    put(s, SATORU)
    wolf = card_named(s, "Young Wolf")
    act(s, "p1", type="move", card_ids=[wolf.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Dose of Dawnglow")
    mana(s, B=1, C=4)
    before = hand(s) - 1  # (Dose leaves the hand as it is cast)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dose of Dawnglow").id, targets=[wolf.id])
    settle(s)
    assert s.state.cards[wolf.id].zone == "p1:battlefield" and hand(s) == before + 1  # returned, not cast: Satoru draws
    check(s)


def test_satoru_does_not_draw_when_the_creature_was_cast_with_mana(cards):
    s = build(cards, [SATORU, "Grizzly Bears"], [])
    put(s, SATORU)
    to_hand(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    before = hand(s) - 1
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:battlefield" and hand(s) == before  # cast and paid for: no card
    check(s)


# --- "During any turn you attacked with …, you may play that card." ----------------------------------------------------------------------------
# 611.2a / 508.1: the exiled card stays playable (the usual timing rules apply) in the turns the condition is met; a card that left exile is spent (400.7h).


def attack_ready(s, name, top=None, *more):
    """Alice's next turn (what is on her table has been there since the turn began; ``top``: a card put on her library after the draw), the creature declared as an
    attacker; stops after the declaration."""
    stops(s)
    next_turn(s)
    if top:
        on_top(s, top)
    attack(s, *(card_named(s, n) for n in (name, *more)))
    return s.state.turn.number


def try_cast(s, name):
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)
    settle(s)


def test_goblin_researcher_card_is_playable_only_in_turns_it_attacked(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Goblin Researcher", "Grizzly Bears"], [])
    on_top(s, "Grizzly Bears")
    to_hand(s, "Goblin Researcher")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Researcher").id)
    settle(s)
    bears = card_named(s, "Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:exile"
    with pytest.raises(ActionError):
        try_cast(s, "Grizzly Bears")  # nothing attacked yet
    turn = attack_ready(s, "Goblin Researcher")
    to_phase(s, "main2", turn=turn)
    try_cast(s, "Grizzly Bears")  # "this creature" attacked this turn
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_goblin_researcher_card_stays_unplayable_when_another_creature_attacked(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Goblin Researcher", "Grizzly Bears", "Young Wolf"], [])
    on_top(s, "Grizzly Bears")
    put(s, "Young Wolf")
    to_hand(s, "Goblin Researcher")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Researcher").id)
    settle(s)
    turn = attack_ready(s, "Young Wolf")  # not the Researcher
    to_phase(s, "main2", turn=turn)
    with pytest.raises(ActionError):
        try_cast(s, "Grizzly Bears")
    check(s)


def test_neyali_exiled_card_is_playable_in_a_turn_a_token_attacked(cards):

    s = build(cards, ["Neyali, Suns' Vanguard", "Raise the Alarm", "Grizzly Bears"], [])
    put(s, "Neyali, Suns' Vanguard")
    to_hand(s, "Raise the Alarm")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Raise the Alarm").id)
    settle(s)
    turn = attack_ready(s, "Soldier", top="Grizzly Bears")  # a token attacks: Neyali exiles the top card
    settle(s)
    bears = card_named(s, "Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:exile"
    to_phase(s, "main2", turn=turn)
    try_cast(s, "Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_neyali_exiled_card_waits_for_the_next_turn_a_token_attacks(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Neyali, Suns' Vanguard", "Raise the Alarm", "Grizzly Bears"], [])
    put(s, "Neyali, Suns' Vanguard")
    to_hand(s, "Raise the Alarm")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Raise the Alarm").id)
    settle(s)
    turn = attack_ready(s, "Soldier", top="Grizzly Bears")
    settle(s)
    to_phase(s, "main1", turn=turn + 2)  # the next turn, before any attack
    with pytest.raises(ActionError):
        try_cast(s, "Grizzly Bears")
    check(s)


def test_boros_strike_captain_card_is_playable_in_a_turn_three_creatures_attacked(cards):
    s = build(cards, ["Boros Strike-Captain", "Grizzly Bears", "Young Wolf", "Albino Troll"], [])
    for n in ("Boros Strike-Captain", "Grizzly Bears", "Young Wolf"):
        put(s, n)
    turn = attack_ready(s, "Boros Strike-Captain", "Albino Troll", "Grizzly Bears", "Young Wolf")  # battalion: three attackers
    settle(s)
    troll = card_named(s, "Albino Troll")
    assert s.state.cards[troll.id].zone == "p1:exile"
    to_phase(s, "main2", turn=turn)
    try_cast(s, "Albino Troll")
    assert s.state.cards[troll.id].zone == "p1:battlefield"
    check(s)


def test_neriv_cards_are_playable_in_a_turn_a_commander_attacked(cards):
    s = build(cards, ["Neriv, Crackling Vanguard", "Raise the Alarm", "Grizzly Bears"], [])
    put(s, "Neriv, Crackling Vanguard")
    put(s, "Krenko, Mob Boss")  # Alice's commander
    to_hand(s, "Raise the Alarm")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Raise the Alarm").id)
    settle(s)
    turn = attack_ready(s, "Neriv, Crackling Vanguard", "Grizzly Bears", "Krenko, Mob Boss")  # one differently named token: one card
    settle(s)
    bears = card_named(s, "Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:exile"
    to_phase(s, "main2", turn=turn)
    try_cast(s, "Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)
