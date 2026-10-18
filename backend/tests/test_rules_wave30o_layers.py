"""Wave 30O: single-object layer effects, real Oracle text (tests/fixtures/wave30o_layers_cards.json, from data/cards.sqlite).

Researched against CR 2026-09-25: the base power and toughness of a creature are set in layer 7b (613.4b, 208.4a), +1/+1 counters and
pumps modify what was set in layer 7c, and the later timestamp wins between two setters (613.7). A continuous effect from a resolving
ability affects the objects it found when it began (611.2c) and reads its values once (611.2d, 608.2h); "until end of turn" ends at
cleanup (514.2) and a permanent that leaves and returns is a new object (400.7).

* "This creature's base power and toughness become equal to that creature's power and toughness until end of turn" (Eldrazi Mimic),
  "… become 4/2 …" (Mirkwood Meditator), "{1}{U}: This creature's base power becomes equal to target creature's power." (Riptide Mangler,
  no duration: it lasts indefinitely, 611.2a), "Its base power and toughness become equal to Galion's …" (Galion), the same for a group
  (Tanazir Quandrix).
* "has base power and toughness 4/4, gains all creature types, and gains flying" (Wings of Velis Vel, Glamer Gifter).
* "becomes a blue and red Dragon with base power and toughness 4/4, loses all abilities, and gains flying" (Dragonshift).
* "has base power and toughness X/X and becomes a Giant in addition to its other types" (Minsc), "becomes an Avatar … and gains flying,
  first strike, lifelink, and hexproof" (Enter the Avatar State), "becomes all colors" (Scrapbasket).

Every scenario checks that replaying the recorded history reproduces the table and that a save and a load keep it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30o_layers_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30o", number=f"L{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer="yes", limit=60):
    """Resolve everything; an optional trigger is answered ``answer`` ("yes" / "no"), any other choice with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=200):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def attack(s, *attackers):
    """Alice attacks Bob with these creatures (long on the table: no summoning sickness); the attack triggers are put on the stack."""
    for c in attackers:
        s.state.rules.controlled_since[c.id].turn = 0
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def ch(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def counter(s, name, delta=1, pid="p1"):
    act(s, "p1", type="counter", card_ids=[card_named(s, name, pid).id], kind="+1/+1", delta=delta)


def cast(s, name, target=None, pid="p1", answer="yes", **pool):
    c = to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": [card_named(s, target).id]} if target else {}))
    settle(s, answer)
    return c


def test_wordings_are_covered(cards):
    from app.rules import coverage

    for name in ("Eldrazi Mimic", "Riptide Mangler", "Galion, Elvenking's Butler", "Tanazir Quandrix", "Mirkwood Meditator",
                 "Minsc, Beloved Ranger", "Wings of Velis Vel", "Dragonshift", "Glamer Gifter", "Enter the Avatar State",
                 "Scrapbasket", "Exuberant Wolfbear"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def chars(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])


def next_turn(s):
    """To the main phase of the next turn of Alice's (cleanup, 514.2, has ended the "until end of turn" effects)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)


# -- Eldrazi Mimic: "base power and toughness become equal to that creature's power and toughness until end of turn" ---------------------
def test_mimic_takes_the_entering_creatures_stats_as_its_base_and_counters_stack_on_top(cards):
    s = build(cards, ["Eldrazi Mimic", "Juggernaut"])
    put(s, "Eldrazi Mimic")
    cast(s, "Juggernaut", C=4)  # a colorless creature enters: "you may have …"
    assert pt(s, "Eldrazi Mimic") == (5, 3)  # 613.4b: layer 7b sets the base
    counter(s, "Eldrazi Mimic")
    assert pt(s, "Eldrazi Mimic") == (6, 4)  # 613.4c: the counter modifies what 7b set
    counter(s, "Juggernaut", 2)
    assert pt(s, "Eldrazi Mimic") == (6, 4)  # 611.2d, 608.2h: Juggernaut's numbers were read once, as the ability resolved
    check(s)
    next_turn(s)
    assert pt(s, "Eldrazi Mimic") == (3, 2)  # 514.2: back to its own 2/1, the counter stays
    check(s)


def test_mimic_declined_and_a_colored_creature_change_nothing(cards):
    s = build(cards, ["Eldrazi Mimic", "Juggernaut", "Grizzly Bears"])
    put(s, "Eldrazi Mimic")
    cast(s, "Grizzly Bears", G=1, C=1)  # not colorless: no trigger
    assert pt(s, "Eldrazi Mimic") == (2, 1)
    cast(s, "Juggernaut", answer="no", C=4)
    assert pt(s, "Eldrazi Mimic") == (2, 1)
    check(s)


def test_mimic_that_leaves_and_returns_is_a_new_object_without_the_effect(cards):
    s = build(cards, ["Eldrazi Mimic", "Juggernaut"])
    mimic = put(s, "Eldrazi Mimic")
    cast(s, "Juggernaut", C=4)
    assert pt(s, "Eldrazi Mimic") == (5, 3)
    act(s, "p1", type="move", card_ids=[mimic.id], to={"zone": "hand"})
    put(s, "Eldrazi Mimic")  # 400.7: a new object, the effect found the old one
    assert pt(s, "Eldrazi Mimic") == (2, 1)
    check(s)


@pytest.mark.parametrize("wings_first", [True, False])
def test_the_later_base_setter_wins_whatever_the_order_of_the_cards(cards, wings_first):
    """613.7: of two layer 7b setters, the one that began later applies last. Wings of Velis Vel (4/4) and Mimic's 5/3."""
    s = build(cards, ["Eldrazi Mimic", "Juggernaut", "Wings of Velis Vel"])
    put(s, "Eldrazi Mimic")
    if wings_first:
        cast(s, "Wings of Velis Vel", "Eldrazi Mimic", U=1, C=1)
        assert pt(s, "Eldrazi Mimic") == (4, 4)
    cast(s, "Juggernaut", C=4)
    if not wings_first:
        assert pt(s, "Eldrazi Mimic") == (5, 3)
        cast(s, "Wings of Velis Vel", "Eldrazi Mimic", U=1, C=1)
    assert pt(s, "Eldrazi Mimic") == ((5, 3) if wings_first else (4, 4))
    check(s)


# -- Riptide Mangler: "{1}{U}: This creature's base power becomes equal to target creature's power." (no duration: indefinitely, 611.2a) --
def test_riptide_mangler_keeps_the_power_it_took_through_turns_and_humility_comes_and_goes(cards):
    s = build(cards, ["Riptide Mangler", "Juggernaut", "Humility"])
    mangler = put(s, "Riptide Mangler")
    jug = put(s, "Juggernaut")
    assert pt(s, "Riptide Mangler") == (0, 3)
    mana(s, U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=mangler.id, ability=0, targets=[jug.id])
    settle(s)
    assert pt(s, "Riptide Mangler") == (5, 3)  # only the power is set (613.4b); the toughness is its own
    counter(s, "Juggernaut", 3)
    assert pt(s, "Riptide Mangler") == (5, 3)  # read once as it resolved (611.2d)
    next_turn(s)
    assert pt(s, "Riptide Mangler") == (5, 3)  # no cleanup end: it lasts indefinitely
    check(s)
    hum = cast(s, "Humility", W=2, C=2)  # a later timestamp in layer 7b: everything is 1/1 (and the Mangler has lost its ability)
    assert pt(s, "Riptide Mangler") == (1, 1)
    assert not [a for a in chars(s, "Riptide Mangler").abilities if a.kind == "activated"]
    check(s)
    act(s, "p1", type="move", card_ids=[hum.id], to={"zone": "graveyard"})
    assert pt(s, "Riptide Mangler") == (5, 3)  # the effect never stopped, it was only overridden
    act(s, "p1", type="move", card_ids=[mangler.id], to={"zone": "hand"})
    put(s, "Riptide Mangler")
    assert pt(s, "Riptide Mangler") == (0, 3)  # 400.7: a new object
    check(s)


# -- Mirkwood Meditator: "you may have this creature's base power and toughness become 4/2 until end of turn" --------------------------
def test_mirkwood_meditator_swaps_to_4_2_on_landfall_and_counters_sit_on_top(cards):
    s = build(cards, ["Mirkwood Meditator", "Forest"])
    put(s, "Mirkwood Meditator")
    assert pt(s, "Mirkwood Meditator") == (2, 4)
    land = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    settle(s)
    assert pt(s, "Mirkwood Meditator") == (4, 2)
    counter(s, "Mirkwood Meditator")
    assert pt(s, "Mirkwood Meditator") == (5, 3)
    check(s)
    next_turn(s)
    assert pt(s, "Mirkwood Meditator") == (3, 5)
    check(s)


# -- Galion and Tanazir: another object's / a group's base power and toughness take this creature's ----------------------------------
def test_galion_sets_the_chosen_creatures_base_to_its_own_power_and_toughness(cards):
    s = build(cards, ["Galion, Elvenking's Butler", "Grizzly Bears"])
    galion = put(s, "Galion, Elvenking's Butler")
    put(s, "Grizzly Bears")
    counter(s, "Galion, Elvenking's Butler")  # 5/5 when the ability resolves: the effective power and toughness are read
    attack(s, galion)
    settle(s)
    assert pt(s, "Grizzly Bears") == (5, 5)
    assert pt(s, "Galion, Elvenking's Butler") == (5, 5)
    counter(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (6, 6)
    check(s)
    next_turn(s)
    assert pt(s, "Grizzly Bears") == (3, 3)
    check(s)


def test_tanazir_sets_the_creatures_there_when_it_resolves_and_not_those_that_come_later(cards):
    s = build(cards, ["Tanazir Quandrix", "Grizzly Bears", "Mirkwood Meditator", "Juggernaut"])
    tanazir = put(s, "Tanazir Quandrix")
    put(s, "Grizzly Bears")
    put(s, "Mirkwood Meditator")
    attack(s, tanazir)
    settle(s)
    assert pt(s, "Grizzly Bears") == (4, 4) and pt(s, "Mirkwood Meditator") == (4, 4)
    put(s, "Juggernaut")  # 611.2c: not there when the ability resolved
    assert pt(s, "Juggernaut") == (5, 3)
    check(s)
    next_turn(s)
    assert pt(s, "Grizzly Bears") == (2, 2) and pt(s, "Mirkwood Meditator") == (2, 4)
    check(s)


# -- Wings of Velis Vel, Glamer Gifter: "has base power and toughness 4/4, gains all creature types, and gains flying" ---------------------
def test_wings_of_velis_vel_sets_the_base_gives_every_creature_type_and_flying_until_end_of_turn(cards):
    s = build(cards, ["Wings of Velis Vel", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    cast(s, "Wings of Velis Vel", "Grizzly Bears", U=1, C=1)
    c = chars(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (4, 4) and "flying" in c.granted and {"Bear", "Dragon", "Elf", "Human"} <= set(c.subtypes)
    counter(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (5, 5)  # 7c on top of the 7b setting
    check(s)
    next_turn(s)
    c = chars(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (3, 3) and "flying" not in c.granted and set(c.subtypes) == {"Bear"}
    check(s)


def test_glamer_gifter_gives_the_chosen_creature_4_4_and_every_creature_type_but_no_flying(cards):
    s = build(cards, ["Glamer Gifter", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    cast(s, "Glamer Gifter", U=1, C=1)
    c = chars(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (4, 4) and "flying" not in c.granted and "Faerie" in c.subtypes
    assert pt(s, "Glamer Gifter") == (1, 2)  # "other target creature"
    check(s)


# -- Dragonshift: "becomes a blue and red Dragon with base power and toughness 4/4, loses all abilities, and gains flying" ------------
@pytest.mark.parametrize("avatar_first", [True, False])
def test_dragonshift_takes_the_abilities_that_came_before_it_and_keeps_those_that_come_after(cards, avatar_first):
    """613.7 with 613.1f: the loss applies to every ability the creature had with an earlier timestamp (Enter the Avatar State's four
    keywords included); the flying Dragonshift itself grants, and anything granted later, stay."""
    s = build(cards, ["Dragonshift", "Enter the Avatar State", "Mirkwood Meditator", "Forest"])
    put(s, "Mirkwood Meditator")
    avatar = ("Enter the Avatar State", "Mirkwood Meditator", dict(G=1, W=1, U=2, C=2))
    dragon = ("Dragonshift", "Mirkwood Meditator", dict(U=1, R=1, C=1))
    for name, target, pool in ([avatar, dragon] if avatar_first else [dragon, avatar]):
        cast(s, name, target, **pool)
    c = chars(s, "Mirkwood Meditator")
    four ={"flying", "first strike", "lifelink", "hexproof"}
    assert set(c.granted) == ({"flying"} if avatar_first else four)
    assert set(c.subtypes) == ({"Dragon"} if avatar_first else {"Dragon", "Avatar"})  # 205.1a: "a Dragon" sets the creature types
    assert pt(s, "Mirkwood Meditator") == (4, 4) and set(c.colors) == {"U", "R"} and not c.abilities
    land = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    settle(s)
    assert pt(s, "Mirkwood Meditator") == (4, 4)  # its landfall ability is gone: no 4/2
    check(s)
    next_turn(s)
    c = chars(s, "Mirkwood Meditator")
    assert pt(s, "Mirkwood Meditator") == (2, 4) and set(c.subtypes) == {"Elf", "Druid"} and set(c.colors) == {"U"} and c.abilities
    check(s)


# -- Minsc, Beloved Ranger: "has base power and toughness X/X and becomes a Giant in addition to its other types" -------------------
def test_minsc_sets_x_x_and_adds_giant_and_the_later_activation_wins(cards):
    s = build(cards, ["Minsc, Beloved Ranger", "Grizzly Bears"])
    minsc = put(s, "Minsc, Beloved Ranger")
    put(s, "Grizzly Bears")
    ability = next(i for i, a in enumerate(chars(s, "Minsc, Beloved Ranger").abilities) if a.kind == "activated")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=minsc.id, ability=ability, targets=[card_named(s, "Grizzly Bears").id], x_value=3)
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3) and set(chars(s, "Grizzly Bears").subtypes) == {"Bear", "Giant"}  # 205.1b: in addition
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=minsc.id, ability=ability, targets=[card_named(s, "Grizzly Bears").id], x_value=5)
    settle(s)
    assert pt(s, "Grizzly Bears") == (5, 5)  # 613.7: the later setter, not the larger
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=minsc.id, ability=ability, targets=[card_named(s, "Grizzly Bears").id], x_value=1)
    settle(s)
    assert pt(s, "Grizzly Bears") == (1, 1)
    counter(s, "Grizzly Bears")
    assert pt(s, "Grizzly Bears") == (2, 2)
    check(s)
    next_turn(s)
    assert pt(s, "Grizzly Bears") == (3, 3) and set(chars(s, "Grizzly Bears").subtypes) == {"Bear"}
    check(s)


# -- Scrapbasket: "this creature becomes all colors until end of turn" (105.1, 613.1e) ------------------------------------------
def test_scrapbasket_is_all_five_colors_until_end_of_turn(cards):
    s = build(cards, ["Scrapbasket"])
    sb = put(s, "Scrapbasket")
    assert not chars(s, "Scrapbasket").colors
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sb.id, ability=0)
    settle(s)
    assert set(chars(s, "Scrapbasket").colors) == {"W", "U", "B", "R", "G"}
    check(s)
    next_turn(s)
    assert not chars(s, "Scrapbasket").colors
    check(s)


def test_overloaded_dragonshift_changes_the_creatures_there_when_it_resolves_only(cards):
    """702.96a: "each creature you control becomes a blue and red Dragon …, loses all abilities, and gains flying"; 611.2c: a creature that
    comes later is not one of them (and keeps its abilities)."""
    s = build(cards, ["Dragonshift", "Mirkwood Meditator", "Grizzly Bears", "Juggernaut"])
    put(s, "Mirkwood Meditator")
    put(s, "Grizzly Bears")
    dragonshift = to_hand(s, "Dragonshift")
    mana(s, U=2, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=dragonshift.id, alt_cost=f"{dragonshift.id}:1")
    settle(s)
    for name in ("Mirkwood Meditator", "Grizzly Bears"):
        c = chars(s, name)
        assert pt(s, name) == (4, 4) and set(c.subtypes) == {"Dragon"} and set(c.colors) == {"U", "R"} and "flying" in c.granted, name
    put(s, "Juggernaut")
    assert pt(s, "Juggernaut") == (5, 3) and chars(s, "Juggernaut").abilities and not chars(s, "Juggernaut").colors
    check(s)


# -- Shape Stealer: "that creature" is the one on the other side of the block (509.3d), not Shape Stealer itself ------------------------
def test_shape_stealer_copies_the_blockers_power_and_toughness_not_its_own(cards):
    s = build(cards, ["Shape Stealer"], ["Grizzly Bears"])
    stealer = put(s, "Shape Stealer")
    bears = put(s, "Grizzly Bears", "p2")
    counter(s, "Grizzly Bears", pid="p2")  # a 3/3 blocker
    attack(s, stealer)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": stealer.id}])
    settle(s)  # (the trigger resolved before combat damage: 613.4b set 3/3 from the blocker, 608.2h, not Shape Stealer's own 1/1 …)
    assert [(e.layer, e.power, e.toughness) for e in s.state.rules.effects] == [("7b", 3, 3)]
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # … so it dealt 3 damage to the 3/3 blocker (a 1/1 would not have killed it)
    check(s)
