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
from tests.test_rules_wave111d_costs import answer, cast, ch, counters
from tests.wave9c_kit import build, check, life, mana, put

EXTRA = [
    real("I'm a Doctor, Not a . . .", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature you control. Untap it. Until end of turn, it gets +1/+1 and "
         "becomes a Doctor. (It loses all other creature types.)", None, "G"),
    real("Daniels, Temporal Agent", "{2}{B/G}{B/G}", 4, "Legendary Creature — Human Advisor", "When Daniels enters, return target creature card from your "
         "graveyard to your hand.\n{2}, Put this card from your graveyard on the bottom of your library: You gain 2 life.", ("3", "1"), "BG"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Centaur Courser", "{2}{G}", 3, "Creature — Centaur Warrior", "", ("3", "3"), "G"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
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
