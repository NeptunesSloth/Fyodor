"""Wave 100E: counts and X that size targets, tokens and keyword actions (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json); every scenario checks the replay and a save and a load.

* "up to X target …, where X is …": the number of targets as they are chosen (601.2c), the amount again as it resolves (608.2h:
  Prismabasher, the 2025-11-17 ruling; Agility Bobblehead "as you activate this ability").
* Another player does a keyword action: "Its controller incubates X" (Excise the Imperfect), "amasses Goblins X" (Azog, 701.47a), X the
  object as it last existed (608.2h).
* "X times" / the cast X of an enters trigger (Progenitor Exarch, Fractal Harness), "that many" (Last Stand), "this way" (Balin).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand
from tests.wave100e_kit import answer, chars, full_control, hand, pick, set_hand, tokens, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def all_named(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def cast_in(s, name, x=None, **m):
    """Cast it from hand with this mana (its enters trigger follows)."""
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"x_value": x} if x is not None else {}))
    while s.state.rules.decision is None and c.id in s.state.zones.get("stack", []):
        act(s, s.state.rules.priority, type="pass_priority")
    return c


def put_all(s, name, pid="p1"):
    for c in all_named(s, name, pid):
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})


# -- Balin, Loremaster ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("rings", "dealt"), [(2, 3), (1, 0)])
def test_balin_discards_draws_that_many_and_burns_with_an_enduring_story(cards, rings, dealt):
    """Balin (legendary) and two artifacts: an enduring story (702.195b), so 3 discarded = 3 drawn and 3 to each opponent; one artifact: no
    damage."""
    s = build(cards, ["Balin, Loremaster", "Sol Ring", "Sol Ring"])
    for c in all_named(s, "Sol Ring")[:rings]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    balin = to_hand(s, "Balin, Loremaster")
    set_hand(s, "p1", 4)
    held = [c for c in s.state.zones["p1:hand"] if c != balin.id]
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=balin.id)
    answer(s, "yes")
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in held) and hand(s) == 3 and life(s, "p2") == 40 - dealt
    check(s)


def test_balin_declined_keeps_the_hand(cards):
    s = build(cards, ["Balin, Loremaster", "Sol Ring", "Sol Ring"])
    put_all(s, "Sol Ring")
    balin = to_hand(s, "Balin, Loremaster")
    set_hand(s, "p1", 3)
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=balin.id)
    answer(s, "no")
    assert hand(s) == 2 and life(s, "p2") == 40
    check(s)


# -- Prismabasher ---------------------------------------------------------------------------------------------------------------------------------
def prisma(cards):
    s = build(cards, ["Prismabasher", "Llanowar Elves", "Monastery Swiftspear", "Benalish Hero"])
    elves, swift, hero = put(s, "Llanowar Elves"), put(s, "Monastery Swiftspear"), put(s, "Benalish Hero")
    return s, elves, swift, hero


def test_prismabasher_targets_up_to_the_colors_and_pumps_by_them(cards):
    """Green, red and white permanents: up to three targets, +3/+3 each."""
    s, elves, swift, hero = prisma(cards)
    cast_in(s, "Prismabasher", G=2, C=4)
    answer(s, elves.id, swift.id, hero.id)
    assert pt(s, "Llanowar Elves") == (4, 4) and pt(s, "Monastery Swiftspear") == (4, 5) and pt(s, "Benalish Hero") == (4, 4)
    check(s)


def test_prismabasher_counts_again_as_it_resolves(cards):
    """The ruling of 2025-11-17: three colors as it triggers (three targets), two as it resolves (the white Hero left): +2/+2."""
    s, elves, swift, hero = prisma(cards)
    cast_in(s, "Prismabasher", G=2, C=4)
    full_control(s)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[elves.id, swift.id, hero.id])
    act(s, "p1", type="move", card_ids=[hero.id], to={"player": "p1", "zone": "hand"})
    answer(s)
    assert pt(s, "Llanowar Elves") == (3, 3) and pt(s, "Monastery Swiftspear") == (3, 4)
    check(s)


# -- Agility Bobblehead ---------------------------------------------------------------------------------------------------------------------------
def test_agility_bobblehead_up_to_x_targets_gain_haste_and_evasion(cards):
    """Two Bobbleheads: two targets gain haste and "can't be blocked this turn except by creatures with haste"; a third is too many."""
    s = build(cards, ["Agility Bobblehead", "Endurance Bobblehead", "Grizzly Bears", "Llanowar Elves", "Benalish Hero"])
    agility = put(s, "Agility Bobblehead")
    put(s, "Endurance Bobblehead")
    bears, elves, hero = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Benalish Hero")
    mana(s, C=3)
    index = ability_index(s, agility, "Up to X target")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=agility.id, ability=index, targets=[bears.id, elves.id, hero.id], target_counts=[3])
    act(s, "p1", type="activate_ability", card_id=agility.id, ability=index, targets=[bears.id, elves.id], target_counts=[2])
    answer(s)
    for c in (bears, elves):
        ch = chars(s, c)
        assert "haste" in ch.keywords and any(r.startswith("cant_be_blocked_except_by:") for r in ch.imposed)
    assert "haste" not in chars(s, hero).keywords
    check(s)


# -- Last Stand -----------------------------------------------------------------------------------------------------------------------------------
def test_last_stand_counts_each_basic_land_type(cards):
    """Two Swamps, one Mountain, one Forest, one Plains, two Islands: Bob loses 4, the Wall is dealt 1, one Saproling, Alice gains 2, draws
    two cards and then discards that many."""
    s = build(cards, ["Last Stand", "Swamp", "Swamp", "Mountain", "Probe Plains", "Island", "Island", *["Opt"] * 5], ["Probe Wall"], forests=1)
    for name in ("Swamp", "Mountain", "Probe Plains", "Island", "Forest"):
        put_all(s, name)
    wall = put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Last Stand")
    set_hand(s, "p1", 1)
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2", wall.id], target_counts=[1, 1])
    answer(s)
    assert life(s, "p2") == 36 and s.state.cards[wall.id].damage == 1 and len(tokens(s, "Saproling", "p1")) == 1
    assert life(s, "p1") == 42 and hand(s) == 0 and len(s.state.zones["p1:graveyard"]) == 3  # (Last Stand and the two discarded cards)
    check(s)


# -- Gloom Ripper ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("second", [True, False])
def test_gloom_ripper_pumps_one_and_shrinks_the_other_by_elves(cards, second):
    """Gloom Ripper and Llanowar Elves on the battlefield, Elvish Visionary in the graveyard: X 3; up to one opponent's creature."""
    s = build(cards, ["Gloom Ripper", "Llanowar Elves", "Elvish Visionary"], ["Probe Wall"])
    elves = put(s, "Llanowar Elves")
    visionary = card_named(s, "Elvish Visionary")
    act(s, "p1", type="move", card_ids=[visionary.id], to={"player": "p1", "zone": "graveyard"})
    wall = put(s, "Probe Wall", "p2")
    cast_in(s, "Gloom Ripper", B=2, C=3)
    pick(s, "choose_cards", elves.id)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[wall.id] if second else [])
    answer(s)
    assert pt(s, "Llanowar Elves") == (4, 1) and pt(s, "Probe Wall", "p2") == ((0, 3) if second else (0, 6))
    check(s)


# -- Excise the Imperfect -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("owner", "victim", "n"), [("p2", "Twisted Abomination", 6), ("p1", "Grizzly Bears", 2)])
def test_excise_the_imperfect_its_controller_incubates_its_mana_value(cards, owner, victim, n):
    s = build(cards, ["Excise the Imperfect", *(["Grizzly Bears"] if owner == "p1" else [])], ["Twisted Abomination"] if owner == "p2" else [])
    target = put(s, victim, owner)
    spell = to_hand(s, "Excise the Imperfect")
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    answer(s)
    made = tokens(s, "Incubator", owner)
    assert zone_of(s, target) == f"{owner}:exile" and len(made) == 1 and made[0].counters.get("+1/+1") == n
    assert not tokens(s, "Incubator", "p2" if owner == "p1" else "p1")
    check(s)


# -- Progenitor Exarch ----------------------------------------------------------------------------------------------------------------------------
def test_progenitor_exarch_incubates_three_x_times(cards):
    s = build(cards, ["Progenitor Exarch"])
    exarch = to_hand(s, "Progenitor Exarch")
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=exarch.id, x_value=2)
    answer(s)
    made = tokens(s, "Incubator", "p1")
    assert len(made) == 2 and all(t.counters.get("+1/+1") == 3 for t in made)
    check(s)


# -- Azog, Moria's Ruin ---------------------------------------------------------------------------------------------------------------------------
def test_azog_their_creature_destroyed_they_amass_its_last_known_power(cards):
    """Bob's 5/3 with a +1/+1 counter: Bob amasses Goblins 6 (a Goblin Army with six counters); Alice draws nothing."""
    s = build(cards, ["Azog, Moria's Ruin"], ["Twisted Abomination"])
    big = put(s, "Twisted Abomination", "p2")
    act(s, "p2", type="counter", card_ids=[big.id], kind="+1/+1", delta=1)
    before = hand(s)
    cast_in(s, "Azog, Moria's Ruin", B=1, C=2)
    answer(s, big.id)
    army = tokens(s, "Goblin Army", "p2")
    assert zone_of(s, big) == "p2:graveyard" and len(army) == 1 and army[0].counters.get("+1/+1") == 6 and hand(s) == before
    assert not tokens(s, "Goblin Army", "p1")
    check(s)


def test_azog_your_own_creature_you_amass_and_draw(cards):
    s = build(cards, ["Azog, Moria's Ruin", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    before = hand(s)
    cast_in(s, "Azog, Moria's Ruin", B=1, C=2)
    answer(s, bears.id)
    army = tokens(s, "Goblin Army", "p1")
    assert zone_of(s, bears) == "p1:graveyard" and army[0].counters.get("+1/+1") == 2 and hand(s) == before + 1
    check(s)


def test_azog_an_indestructible_creature_still_has_its_controller_amass(cards):
    """Not destroyed, it is still "that creature": Bob amasses Goblins 0 — the 0/0 Army is created and dies (701.47a, 704.5f)."""
    s = build(cards, ["Azog, Moria's Ruin"], ["Darksteel Myr"])
    myr = put(s, "Darksteel Myr", "p2")
    cast_in(s, "Azog, Moria's Ruin", B=1, C=2)
    answer(s, myr.id)
    assert zone_of(s, myr) == "p2:battlefield" and not tokens(s, "Goblin Army", "p2")
    assert any("Goblin Army" in " ".join(p.t or p.name or "" for p in entry.parts) for entry in s.state.log)
    check(s)


def test_azog_with_no_target_nobody_amasses(cards):
    s = build(cards, ["Azog, Moria's Ruin"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    cast_in(s, "Azog, Moria's Ruin", B=1, C=2)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert not tokens(s, "Goblin Army", "p1") and not tokens(s, "Goblin Army", "p2")
    check(s)


# -- Fractal Harness ------------------------------------------------------------------------------------------------------------------------------
def test_fractal_harness_makes_an_x_fractal_and_equips_it(cards):
    s = build(cards, ["Fractal Harness"])
    harness = to_hand(s, "Fractal Harness")
    mana(s, G=1, C=5)
    act(s, "p1", type="cast_spell", card_id=harness.id, x_value=3)
    answer(s)
    (fractal,) = tokens(s, "Fractal", "p1")
    assert fractal.counters.get("+1/+1") == 3 and s.state.cards[harness.id].attached_to == fractal.id
    check(s)
