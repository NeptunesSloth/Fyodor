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
from tests.wave9c_kit import build, check, life, mana, pt, put, to_hand
from tests.wave36a_kit import ready

_BRUTAL = 'Activated abilities of nontoken Rebels cost an additional "Sacrifice a land" to activate.'
_DROUGHT = ("At the beginning of your upkeep, sacrifice this enchantment unless you pay {W}{W}.\n"
            'Spells cost an additional "Sacrifice a Swamp" to cast for each black mana symbol in their mana costs.\n'
            'Activated abilities cost an additional "Sacrifice a Swamp" to activate for each black mana symbol in their activation costs.')
_PING = "{T}: This creature deals 1 damage to any target."
_ADD = [
    real('Brutal Suppression', '{R}', 1, 'Enchantment', _BRUTAL, None, 'R'),
    real('Drought', '{2}{W}{W}', 4, 'Enchantment', _DROUGHT, None, 'W'),
    real('Test Rebel 13F', '{1}', 1, 'Creature — Rebel', _PING, ('1', '1'), ''),
    real('Test Human 13F', '{1}', 1, 'Creature — Human', _PING, ('1', '1'), ''),
    real('Test Land 13F', '', 0, 'Land', '{T}: Add {C}.', None, ''),
    real('Test Dark 13F', '{1}{B}{B}', 3, 'Sorcery', 'You gain 3 life.', None, 'B'),
    real('Test Hybrid 13F', '{B/G}{B/G}', 2, 'Sorcery', 'You gain 3 life.', None, 'BG'),
    real('Test Red 13F', '{R}', 1, 'Sorcery', 'You gain 3 life.', None, 'R'),
    real('Test Dark Pinger 13F', '{1}', 1, 'Artifact', "{B}, {T}: This artifact deals 1 damage to any target.", None, ''),
    real('Test Cycler 13F', '{2}{B}', 3, 'Sorcery', "Cycling {B}\nYou gain 3 life.", None, 'B'),
    real('Test Swamp Mana 13F', '{1}', 1, 'Artifact', "{B}, {T}: Add {B}{B}.", None, ''),
]
_BASE.extend(_ADD)
_DESECRATOR = ("Menace\nWhen this creature enters or dies, exile another card from a graveyard. When you do, choose one \u2014\n"
               "\u2022 Remove X counters from target permanent, where X is the mana value of the exiled card.\n"
               "\u2022 Target creature an opponent controls gets -X/-X until end of turn, where X is the mana value of the exiled card.")
_BASE.extend([
    real('Cemetery Desecrator', '{4}{B}{B}', 6, 'Creature \u2014 Zombie', _DESECRATOR, ('4', '4'), 'B'),
    real('Test Three 13F', '{2}{G}', 3, 'Creature \u2014 Elf', '', ('1', '1'), 'G'),
    real('Test Doom 13F', '{B}', 1, 'Instant', 'Destroy target creature.', None, 'B'),
    real('Test Big 13F', '{3}', 3, 'Creature \u2014 Golem', '', ('5', '5'), ''),
])
NAMES = ["Brutal Suppression", "Drought", "Cemetery Desecrator"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _many(s, name, n):
    """n different copies of a card from the library, onto the battlefield."""
    out = [c for c in s.state.cards.values() if c.name == name and c.owner == "p1" and c.zone == "p1:library"][:n]
    act(s, "p1", type="move", card_ids=[c.id for c in out], to={"player": "p1", "zone": "battlefield"})
    return out


def _lands(s, n):
    return _many(s, "Test Land 13F", n)


def _zone(s, card):
    return s.state.cards[card.id].zone


def test_brutal_suppression_taxes_a_rebel_only(cards):
    """118.8: the Rebel's activation sacrifices a land (its controller's choice); a Human is not taxed; without a land it cannot be activated."""
    s = build(cards, ["Brutal Suppression", "Test Rebel 13F", "Test Human 13F", "Test Land 13F", "Test Land 13F", "Test Land 13F"])
    put(s, "Brutal Suppression")
    rebel, human = put(s, "Test Rebel 13F"), put(s, "Test Human 13F")
    ready(s, "Test Rebel 13F")
    ready(s, "Test Human 13F")
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
    s = build(cards, ["Test Rebel 13F", "Test Land 13F"])
    rebel = put(s, "Test Rebel 13F")
    land, = _lands(s, 1)
    ready(s, "Test Rebel 13F")
    activate(s, "p1", rebel, "", targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and _zone(s, land) == "p1:battlefield"
    check(s)


def _drought(cards, deck, swamps):
    s = build(cards, ["Drought", *deck, *["Swamp"] * 3])
    put(s, "Drought")
    got = _many(s, "Swamp", swamps) if swamps else []
    return s, got


@pytest.mark.parametrize(("spell", "need"), [("Test Dark 13F", 2), ("Test Hybrid 13F", 2), ("Test Red 13F", 0)])
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
    s, (swamp,) = _drought(cards, ["Test Dark Pinger 13F"], 1)
    pinger = put(s, "Test Dark Pinger 13F")
    ready(s, "Test Dark Pinger 13F")
    mana(s, B=1)
    activate(s, "p1", pinger, "", targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and _zone(s, swamp) == "p1:graveyard"
    check(s)


def test_drought_mana_ability_and_cycling_with_black_symbols_are_refused(cards):
    """Not automated: the tax is not paid for them, so they are not offered / refused."""
    s, _ = _drought(cards, ["Test Swamp Mana 13F", "Test Cycler 13F"], 1)
    src = put(s, "Test Swamp Mana 13F")
    ready(s, "Test Swamp Mana 13F")
    mana(s, B=1)
    with pytest.raises(ActionError):
        activate(s, "p1", src, "")
    cyc = to_hand(s, "Test Cycler 13F")
    with pytest.raises(ActionError, match="Drought"):
        act(s, "p1", type="activate_ability", card_id=cyc.id, ability=ability_index(s, cyc, "Cycling"))
    assert _zone(s, cyc) == "p1:hand"



def _desecrate(cards, mine=(), theirs=()):
    s = build(cards, ["Cemetery Desecrator", "Test Three 13F", *mine], ["Test Three 13F", "Test Big 13F", *theirs])
    mana(s, B=2, C=4)
    return s


def _gy(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def _next(s):
    """Pass priority until a decision is asked (returned)."""
    for _ in range(20):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def _pick(s, label=None, card=None):
    d = _next(s)
    ids = [o.id for o in d.options if (label is None or label in o.label) and (card is None or o.card_id == card)][:1]
    assert ids, [o.label for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def _power(s, c):
    return pt(s, c.name, c.owner)


def test_desecrator_enters_exile_then_minus_x(cards):
    """603.12, 608.2h: X is the exiled card's mana value (3): the chosen opposing creature gets -3/-3; the exiled card is in exile."""
    s = _desecrate(cards)
    gone = _gy(s, "Test Three 13F", "p2")
    big = put(s, "Test Big 13F", "p2")
    cast(s, "Cemetery Desecrator")
    _pick(s, "-X/-X")
    _pick(s, card=big.id)
    answer(s)
    assert _zone(s, gone) == "p2:exile" and _power(s, big) == (2, 2)  # 5/5 with -3/-3
    check(s)


def test_desecrator_remove_x_counters_and_the_pick_among_graveyards(cards):
    """Two cards in graveyards: the controller picks (608.2d); X = 3 counters come off the chosen permanent (two of five stay), the other card stays."""
    s = _desecrate(cards, mine=("Test Big 13F",))
    three, big_gy = _gy(s, "Test Three 13F", "p1"), _gy(s, "Test Big 13F", "p2")
    stay = put(s, "Test Big 13F", "p1")
    act(s, "p1", type="set_counter", card_id=stay.id, kind="+1/+1", value=5)
    cast(s, "Cemetery Desecrator")
    _pick(s, card=three.id)  # which graveyard card
    _pick(s, "Remove X")
    _pick(s, card=stay.id)
    answer(s)
    assert _zone(s, three) == "p1:exile" and _zone(s, big_gy) == "p2:graveyard"
    assert s.state.cards[stay.id].counters.get("+1/+1") == 2
    check(s)


def test_desecrator_nothing_to_exile_means_no_reflexive_trigger(cards):
    s = _desecrate(cards)
    cast(s, "Cemetery Desecrator")
    answer(s)
    assert s.state.rules.decision is None and not s.state.zones.get("stack")
    check(s)


def test_desecrator_dies_exiles_another_card_never_itself(cards):
    s = build(cards, ["Cemetery Desecrator", "Test Three 13F", "Test Doom 13F"], ["Test Three 13F", "Test Big 13F"])
    mana(s, B=4, C=4)
    big = put(s, "Test Big 13F", "p2")
    des = put(s, "Cemetery Desecrator")
    answer(s)  # its enters trigger finds no other card
    gone = _gy(s, "Test Three 13F", "p2")
    cast(s, "Test Doom 13F", [des.id])
    _pick(s, card=gone.id)  # the Doom is in a graveyard too; the Desecrator itself is no choice (it is "another card")
    _pick(s, "-X/-X")
    _pick(s, card=big.id)
    answer(s)
    assert _zone(s, gone) == "p2:exile" and _zone(s, des) == "p1:graveyard" and _power(s, big) == (2, 2)
    check(s)
