"""Wave 111D: Star Trek one-off wordings (app/rules/wave111d_cards.py). Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a
save and a load.

* I'm a Doctor, Not a . . .: "Until end of turn, it gets +1/+1 and becomes a Doctor." (205.1a: the new creature type replaces the old ones, as its
  reminder says; both effects end at cleanup, 514.2).
* Daniels, Temporal Agent: "{2}, Put this card from your graveyard on the bottom of your library: You gain 2 life." (113.6m: only from the graveyard).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave111d_costs import answer, build3, cast, ch, counters
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real("I'm a Doctor, Not a . . .", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature you control. Untap it. Until end of turn, it gets +1/+1 and "
         "becomes a Doctor. (It loses all other creature types.)", None, "G"),
    real("Daniels, Temporal Agent", "{2}{B/G}{B/G}", 4, "Legendary Creature — Human Advisor", "When Daniels enters, return target creature card from your "
         "graveyard to your hand.\n{2}, Put this card from your graveyard on the bottom of your library: You gain 2 life.", ("3", "1"), "BG"),
    real("Tasha Yar, Out of Time", "{1}{R}", 2, "Legendary Creature — Human Officer", "Haste\nWhen Tasha Yar dies, exile the top card of your library. "
         "Until the end of your next turn, you may play that card.\n{2}{R}, Exile this card from your graveyard: Create a token that's a copy of this card. "
         "Sacrifice it at the beginning of the next end step. Activate only as a sorcery.", ("2", "1"), "R"),
    real("Dathon, His Heart Open", "{G}{U}{R}", 3, "Legendary Creature — Tamarian Officer", "Whenever you cast an enchantment spell, draw a card. If "
         "it's a Saga spell, Dathon deals 2 damage to each opponent.\n{2}: Choose a counter on target enchantment you control. Put another counter of that "
         "kind on it. Activate only as a sorcery.", ("3", "3"), "GRU"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Centaur Courser", "{2}{G}", 3, "Creature — Centaur Warrior", "", ("3", "3"), "G"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("History of Benalia", "{1}{W}{W}", 3, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice "
         "after III.)\nI, II — Create a 2/2 white Knight creature token with vigilance.\nIII — Knights you control get +2/+1 until end of turn.", None, "W"),
    real("Glorious Anthem", "{1}{W}{W}", 3, "Enchantment", "Creatures you control get +1/+1.", None, "W"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- I'm a Doctor, Not a . . . -----------------------------------------------------------------------------------------------------------
def test_im_a_doctor_counter_untap_pump_and_only_a_doctor_until_end_of_turn(cards):
    s = build(cards, ["I'm a Doctor, Not a . . .", "Centaur Courser"])
    courser = put(s, "Centaur Courser")
    act(s, "p1", type="tap", card_ids=[courser.id], tapped=True)
    act(s, "p1", type="set_stops", own=["main1", "end"])
    mana(s, G=1)
    cast(s, "I'm a Doctor, Not a . . .", [courser.id])
    answer(s)
    c = ch(s, courser)
    assert counters(s, courser) == 1 and not s.state.cards[courser.id].tapped
    assert c.pt == (5, 5) and c.subtypes == {"Doctor"}  # (3/3, a counter, +1/+1; no longer a Centaur Warrior)
    to_phase(s, "main1", turn=3)
    c = ch(s, courser)
    assert c.pt == (4, 4) and c.subtypes == {"Centaur", "Warrior"}
    check(s)


def test_im_a_doctor_targets_only_your_creatures(cards):
    s = build(cards, ["I'm a Doctor, Not a . . ."], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, G=1)
    with pytest.raises(ActionError):
        cast(s, "I'm a Doctor, Not a . . .", [bears.id])
    check(s)


# -- Daniels, Temporal Agent -------------------------------------------------------------------------------------------------------------
def test_daniels_returns_a_creature_card_and_recycles_himself_from_the_graveyard(cards):
    s = build(cards, ["Daniels, Temporal Agent", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, G=1, C=2)
    daniels = cast(s, "Daniels, Temporal Agent")
    answer(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:hand"
    mana(s, C=2)
    with pytest.raises(ActionError):  # (on the battlefield: the cost can't be paid, 113.6m)
        act(s, "p1", type="activate_ability", card_id=daniels.id, ability=1)
    act(s, "p1", type="move", card_ids=[daniels.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=daniels.id, ability=1)
    assert s.state.zones["p1:library"][-1] == daniels.id  # (the bottom of its owner's library, as the cost is paid)
    answer(s)
    assert life(s, "p1") == 42
    check(s)


# -- Tasha Yar, Out of Time --------------------------------------------------------------------------------------------------------------
def test_tasha_yar_returns_as_a_token_copy_until_the_end_step(cards):
    s = build(cards, ["Tasha Yar, Out of Time"])
    tasha = card_named(s, "Tasha Yar, Out of Time")
    act(s, "p1", type="move", card_ids=[tasha.id], to={"player": "p1", "zone": "graveyard"})  # (from the library: it never died)
    assert not s.state.zones.get("p1:exile")
    act(s, "p1", type="set_stops", own=["main1", "end"])
    mana(s, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=tasha.id, ability=2)
    assert s.state.cards[tasha.id].zone == "p1:exile"  # (exiled as the cost is paid, 602.2)
    answer(s)
    (token,) = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    c = ch(s, token)
    assert c.name == "Tasha Yar, Out of Time" and c.pt == (2, 1) and "Legendary" in c.supertypes and c.subtypes == {"Human", "Officer"}
    assert "haste" in c.keywords
    top = s.state.zones["p1:library"][0]
    to_phase(s, "end")
    answer(s)
    assert token.id not in s.state.zones.get("p1:battlefield", [])  # (sacrificed at the beginning of the end step, 603.7)
    assert s.state.cards[top].zone == "p1:exile"  # (the token died: its own "When Tasha Yar dies" trigger, 700.4)
    check(s)


def test_tasha_yar_activates_only_from_the_graveyard_as_a_sorcery(cards):
    s = build(cards, ["Tasha Yar, Out of Time"])
    tasha = put(s, "Tasha Yar, Out of Time")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):  # (on the battlefield: 113.6m)
        act(s, "p1", type="activate_ability", card_id=tasha.id, ability=2)
    act(s, "p1", type="move", card_ids=[tasha.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_stops", own=["main1", "end"])
    to_phase(s, "end")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):  # (602.5d)
        act(s, "p1", type="activate_ability", card_id=tasha.id, ability=2)
    check(s)


# -- Dathon, His Heart Open --------------------------------------------------------------------------------------------------------------
def knights(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]


def test_dathon_draws_for_each_enchantment_spell_and_burns_for_a_saga(cards):
    s = build3(cards, ["Dathon, His Heart Open", "Glorious Anthem", "History of Benalia"])
    put(s, "Dathon, His Heart Open")
    anthem, saga = to_hand(s, "Glorious Anthem"), to_hand(s, "History of Benalia")
    lib0 = len(s.state.zones["p1:library"])
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=anthem.id)
    answer(s)
    assert len(s.state.zones["p1:library"]) == lib0 - 1 and (life(s, "p2"), life(s, "p3")) == (40, 40)  # (drew one; not a Saga)
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    answer(s)
    assert len(s.state.zones["p1:library"]) == lib0 - 2 and (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 38, 38)
    check(s)


def test_dathon_gives_a_chosen_counter_another_of_its_kind(cards):
    s = build(cards, ["Dathon, His Heart Open", "History of Benalia", "Glorious Anthem"], ["Glorious Anthem"])
    dathon = put(s, "Dathon, His Heart Open")
    mana(s, W=2, C=1)
    saga = cast(s, "History of Benalia")
    answer(s)
    assert counters(s, saga, "lore") == 1 and len(knights(s)) == 1
    anthem = put(s, "Glorious Anthem")
    theirs = put(s, "Glorious Anthem", "p2")
    mana(s, C=2)
    for bad in (theirs, dathon):  # (an opponent's enchantment, a creature: no legal target, 115.1)
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=dathon.id, ability=1, targets=[bad.id])
    act(s, "p1", type="activate_ability", card_id=dathon.id, ability=1, targets=[anthem.id])  # (no counter on it: nothing to choose)
    answer(s)
    assert not s.state.cards[anthem.id].counters
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=dathon.id, ability=1, targets=[saga.id])
    answer(s)
    assert counters(s, saga, "lore") == 2 and len(knights(s)) == 2  # (a lore counter: chapter II triggers, 714.2b)
    check(s)
