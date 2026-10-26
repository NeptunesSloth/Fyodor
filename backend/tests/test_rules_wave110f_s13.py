"""Wave 110F session 13, on real Oracle text. Every scenario checks the replay and a save and a load.

* 118.8, 602.2b: "Activated abilities of nontoken Rebels cost an additional "Sacrifice a land" to activate." (Brutal Suppression): Rebel abilities only, any land.
* 118.8, 107.4e-f, 601.2f: Drought: a Swamp for each black mana symbol (hybrid and Phyrexian included) in a spell's mana cost or an ability's activation cost;
  a mana ability or a cycling activation with a black symbol is not offered / refused (the tax is not automated there).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30r_history import ability_index
from tests.test_rules_wave34b_activated import activate
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, life, mana, put, to_hand
from tests.wave36a_kit import ready

_BRUTAL = 'Activated abilities of nontoken Rebels cost an additional "Sacrifice a land" to activate.'
_DROUGHT = ("At the beginning of your upkeep, sacrifice this enchantment unless you pay {W}{W}.\n"
            'Spells cost an additional "Sacrifice a Swamp" to cast for each black mana symbol in their mana costs.\n'
            'Activated abilities cost an additional "Sacrifice a Swamp" to activate for each black mana symbol in their activation costs.')
_PING = "{T}: This creature deals 1 damage to any target."
_ADD = [
    real('Brutal Suppression', '{R}', 1, 'Enchantment', _BRUTAL, None, 'R'),
    real('Drought', '{2}{W}{W}', 4, 'Enchantment', _DROUGHT, None, 'W'),
    real('Test Rebel 110F', '{1}', 1, 'Creature — Rebel', _PING, ('1', '1'), ''),
    real('Test Human 110F', '{1}', 1, 'Creature — Human', _PING, ('1', '1'), ''),
    real('Test Land 110F', '', 0, 'Land', '{T}: Add {C}.', None, ''),
    real('Test Dark 110F', '{1}{B}{B}', 3, 'Sorcery', 'You gain 3 life.', None, 'B'),
    real('Test Hybrid 110F', '{B/G}{B/G}', 2, 'Sorcery', 'You gain 3 life.', None, 'BG'),
    real('Test Red 110F', '{R}', 1, 'Sorcery', 'You gain 3 life.', None, 'R'),
    real('Test Dark Pinger 110F', '{1}', 1, 'Artifact', "{B}, {T}: This artifact deals 1 damage to any target.", None, ''),
    real('Test Cycler 110F', '{2}{B}', 3, 'Sorcery', "Cycling {B}\nYou gain 3 life.", None, 'B'),
    real('Test Swamp Mana 110F', '{1}', 1, 'Artifact', "{B}, {T}: Add {B}{B}.", None, ''),
]
_BASE.extend(_ADD)
NAMES = ["Brutal Suppression", "Drought"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _many(s, name, n):
    """n different copies of a card from the library, onto the battlefield."""
    out = [c for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone == "p1:library"][:n]
    act(s, "p1", type="move", card_ids=[c.id for c in out], to={"player": "p1", "zone": "battlefield"})
    return out


def _lands(s, n):
    return _many(s, "Test Land 110F", n)


def _zone(s, card):
    return s.state.cards[card.id].zone


def test_brutal_suppression_taxes_a_rebel_only(cards):
    """118.8: the Rebel's activation sacrifices a land (its controller's choice); a Human is not taxed; without a land it cannot be activated."""
    s = build(cards, ["Brutal Suppression", "Test Rebel 110F", "Test Human 110F", "Test Land 110F", "Test Land 110F", "Test Land 110F"])
    put(s, "Brutal Suppression")
    rebel, human = put(s, "Test Rebel 110F"), put(s, "Test Human 110F")
    ready(s, "Test Rebel 110F")
    ready(s, "Test Human 110F")
    activate(s, "p1", human, "", targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and not any(c.zone == "p1:graveyard" for c in s.state.cards.values())
    with pytest.raises(ActionError):
        activate(s, "p1", rebel, "", targets=["p2"])  # no land to sacrifice
    one, two = _lands(s, 2)
    activate(s, "p1", rebel, "", targets=["p2"])
    answer(s, [two.id])
    answer(s)
    assert life(s, "p2") == 38 and _zone(s, two) == "p1:graveyard" and _zone(s, one) == "p1:battlefield"
    check(s)


def test_brutal_suppression_leaves_other_abilities(cards):
    """Without it on the table the Rebel pays no land."""
    s = build(cards, ["Test Rebel 110F", "Test Land 110F"])
    rebel = put(s, "Test Rebel 110F")
    land, = _lands(s, 1)
    ready(s, "Test Rebel 110F")
    activate(s, "p1", rebel, "", targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and _zone(s, land) == "p1:battlefield"
    check(s)


def _drought(cards, deck, swamps):
    s = build(cards, ["Drought", *deck, *["Swamp"] * 3])
    put(s, "Drought")
    got = _many(s, "Swamp", swamps) if swamps else []
    return s, got


@pytest.mark.parametrize(("spell", "need"), [("Test Dark 110F", 2), ("Test Hybrid 110F", 2), ("Test Red 110F", 0)])
def test_drought_spell_one_swamp_per_black_symbol(cards, spell, need):
    """107.4e: a hybrid {B/G} is a black mana symbol; {R} is none. Too few Swamps: the spell cannot be cast; else they are sacrificed."""
    s, swamps = _drought(cards, [spell], need - 1 if need else 0)
    mana(s, B=2, G=2, R=1, C=1)
    if need:
        with pytest.raises(ActionError):
            cast(s, spell)
        swamps += _many(s, "Swamp", 1)
    cast(s, spell)
    if need:
        answer(s, [x.id for x in swamps])
    answer(s)
    assert life(s, "p1") == 43
    assert all(_zone(s, x) == "p1:graveyard" for x in swamps)
    check(s)


def test_drought_taxes_an_activated_ability_by_its_black_symbols(cards):
    s, (swamp,) = _drought(cards, ["Test Dark Pinger 110F"], 1)
    pinger = put(s, "Test Dark Pinger 110F")
    ready(s, "Test Dark Pinger 110F")
    mana(s, B=1)
    activate(s, "p1", pinger, "", targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and _zone(s, swamp) == "p1:graveyard"
    check(s)


def test_drought_mana_ability_and_cycling_with_black_symbols_are_refused(cards):
    """Not automated: the tax is not paid for them, so they are not offered / refused."""
    s, _ = _drought(cards, ["Test Swamp Mana 110F", "Test Cycler 110F"], 1)
    src = put(s, "Test Swamp Mana 110F")
    ready(s, "Test Swamp Mana 110F")
    mana(s, B=1)
    with pytest.raises(ActionError):
        activate(s, "p1", src, "")
    cyc = to_hand(s, "Test Cycler 110F")
    with pytest.raises(ActionError, match="Drought"):
        act(s, "p1", type="activate_ability", card_id=cyc.id, ability=ability_index(s, cyc, "Cycling"))
    assert _zone(s, cyc) == "p1:hand"
