"""The pod's Toph deck (tests/fixtures/soak_decks/toph_metal_bending.txt): its plan, with real Oracle text.

Toph, the First Metalbender makes each nontoken artifact Alice controls a land as well (layer 4, 205.1b): casting Sol Ring is a land entering
(landfall: Tireless Provisioner, Toph, Earthbending Master, Moraug, Scute Swarm), an artifact can be earthbent (701.66a) at her end step, and
what lands get (Chromatic Lantern's mana ability, Bootleggers' Stash's Treasure ability) the artifacts get too. A Treasure or Food token isn't
a land ("nontoken"). Earthbending then grows: counter doublers (616.1: the controller orders them), Annie Joins Up's additional trigger,
Toph, Greatest Earthbender's double strike for land creatures, and the earthbent land comes back when it dies (Amulet of Vigor untaps it).
"""

from __future__ import annotations

import pytest

from app.rules import coverage, sba
from app.rules.view import hints
from tests.game_helpers import act
from tests.pod_c_kit import card, ch, field, mana, put, settle, table, to_hand, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

TOPH = "Toph, the First Metalbender"
EARTHBEND = ("(Target land you control becomes a 0/0 creature with haste that's still a land. Put {n} +1/+1 counters on it. When it dies or is "
             "exiled, return it to the battlefield tapped.)")
EXTRA = [
    real(TOPH, '{1}{R}{G}{W}', 4, 'Legendary Creature — Human Warrior Ally',
         "Nontoken artifacts you control are lands in addition to their other types. (They don't gain the ability to {T} for mana.)\nAt the "
         "beginning of your end step, earthbend 2. " + EARTHBEND.format(n="two"), ("3", "3"), 'GRW'),
    real('Tireless Provisioner', '{2}{G}', 3, 'Creature — Elf Scout',
         'Landfall — Whenever a land you control enters, create a Food token or a Treasure token. (Food is an artifact with "{2}, {T}, Sacrifice '
         'this token: You gain 3 life." Treasure is an artifact with "{T}, Sacrifice this token: Add one mana of any color.")', ("3", "2"), 'G'),
    real('Toph, Earthbending Master', '{3}{G}', 4, 'Legendary Creature — Human Warrior Ally',
         "Landfall — Whenever a land you control enters, you get an experience counter.\nWhenever you attack, earthbend X, where X is the number "
         "of experience counters you have. " + EARTHBEND.format(n="X"), ("2", "4"), 'G'),
    real('Annie Joins Up', '{1}{R}{G}{W}', 4, 'Legendary Enchantment',
         'When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a '
         'legendary creature you control triggers, that ability triggers an additional time.', None, 'GRW'),
    real('Hardened Scales', '{G}', 1, 'Enchantment',
         'If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.',
         None, 'G'),
    real('Branching Evolution', '{2}{G}', 3, 'Enchantment',
         'If one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters are put on that creature '
         'instead.', None, 'G'),
    real('Amulet of Vigor', '{1}', 1, 'Artifact', 'Whenever a permanent you control enters tapped, untap it.', None, ''),
    real('Beast Within', '{2}{G}', 3, 'Instant', 'Destroy target permanent. Its controller creates a 3/3 green Beast creature token.',
         None, 'G'),
    real('Earthbending Lesson', '{3}{G}', 4, 'Sorcery — Lesson', "Earthbend 4. " + EARTHBEND.format(n="four"), None, 'G'),
    real('Chromatic Lantern', '{3}', 3, 'Artifact',
         'Lands you control have "{T}: Add one mana of any color."\n{T}: Add one mana of any color.', None, ''),
    real("Bootleggers' Stash", '{5}{G}', 6, 'Artifact', 'Lands you control have "{T}: Create a Treasure token."', None, 'G'),
    real('Toph, Greatest Earthbender', '{2}{R}{G}', 4, 'Legendary Creature — Human Warrior Ally',
         'When Toph enters, earthbend X, where X is the amount of mana spent to cast her.\nLand creatures you control have double strike.',
         ("3", "3"), 'GR'),
    real('Toph, the Blind Bandit', '{2}{G}', 3, 'Legendary Creature — Human Warrior Ally',
         "When Toph enters, earthbend 2. " + EARTHBEND.format(n="two") + "\nToph's power is equal to the number of +1/+1 counters on lands you "
         "control.", ("*", "3"), 'G'),
    real('Liquimetal Torque', '{2}', 2, 'Artifact',
         '{T}: Add {C}.\n{T}: Target nonland permanent becomes an artifact in addition to its other types until end of turn.', None, ''),
    real('Moraug, Fury of Akoum', '{4}{R}{R}', 6, 'Legendary Creature — Minotaur Warrior',
         "Each creature you control gets +1/+0 for each time it has attacked this turn.\nLandfall — Whenever a land you control enters, if it's "
         "your main phase, there's an additional combat phase after this phase. At the beginning of that combat, untap all creatures you "
         "control.", ("6", "6"), 'R'),
    real('Ashaya, Soul of the Wild', '{3}{G}{G}', 5, 'Legendary Creature — Elemental',
         "Ashaya's power and toughness are each equal to the number of lands you control.\nNontoken creatures you control are Forest lands in "
         "addition to their other types. (They're still affected by summoning sickness.)", ("*", "*"), 'G'),
    real('Scute Swarm', '{2}{G}', 3, 'Creature — Insect',
         "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a "
         "token that's a copy of this creature instead.", ("1", "1"), 'G'),
    real('Thought Vessel', '{2}', 2, 'Artifact', 'You have no maximum hand size.\n{T}: Add {C}.', None, ''),
]
NAMES = [c["name"] for c in EXTRA]


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


def toph(cards, *mine, theirs=()):
    """Alice's Toph deck (Sol Ring, 20 Forests), Toph on the battlefield."""
    s = table(cards, ("Sol Ring", *mine), theirs, commander=TOPH, lands=("Forest", 20))
    put(s, TOPH)
    return s


def pt(s, c):
    c = s.state.cards[c.id]
    return sba.power(c, ch(s, c)), sba.toughness(c, ch(s, c))


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def stop_at(s, active, phase):
    """Full control for Alice: pass until it is ``active``'s ``phase`` with something on the stack or a decision open (a trigger)."""
    act(s, "p1", type="set_prefs", full_control=True)
    for _ in range(80):
        st = s.state
        if st.turn.active_player == active and st.turn.phase == phase and (st.zones.get("stack") or st.rules.decision):
            return
        if st.rules.decision is not None:
            settle(s)
            continue
        act(s, st.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {active} {phase}")


def test_casting_sol_ring_is_a_land_entering_and_the_treasure_is_not_a_land(cards):
    """Sol Ring on the battlefield is an artifact land: Tireless Provisioner and Toph, Earthbending Master see a land enter. The Treasure
    the Provisioner makes is a token: not a land. In the hand, Sol Ring is still just an artifact spell."""
    s = toph(cards, "Tireless Provisioner", "Toph, Earthbending Master")
    put(s, "Tireless Provisioner")
    put(s, "Toph, Earthbending Master")
    sol = to_hand(s, "Sol Ring")
    mana(s, C=1)
    assert sol.id in hints(s.state, "p1", s.cards)["castable"]
    act(s, "p1", type="cast_spell", card_id=sol.id)
    settle(s, "Create a Treasure token")
    assert ch(s, sol).types == {"Artifact", "Land"}
    treasure = next(s.state.cards[i] for i in s.state.zones["p1:battlefield"] if s.state.cards[i].name == "Treasure")
    assert ch(s, treasure).types == {"Artifact"}
    assert s.state.players["p1"].resources.get("experience") == 1
    check(s)


def test_end_step_earthbend_targets_an_artifact_land_twice_with_annie(cards):
    """Annie Joins Up: Toph's end-step trigger triggers an additional time; both earthbend Sol Ring: a 4/4 artifact land creature with
    haste. Bob is told only that Alice is choosing."""
    s = toph(cards, "Annie Joins Up", theirs=["Grizzly Bears"])
    sol = put(s, "Sol Ring")
    put(s, "Annie Joins Up")
    stop_at(s, "p1", "end")
    settle(s, stop_at=f"{TOPH}: choose a target")
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["Sol Ring"]
    assert (s.view("p2")["rules"]["decision"] or {}).get("options") is None
    settle(s, "Sol Ring", "Sol Ring")
    assert counters(s, sol) == 4 and pt(s, sol) == (4, 4)
    assert ch(s, sol).types == {"Artifact", "Land", "Creature"} and "haste" in ch(s, sol).keywords
    check(s)


def test_counter_doublers_on_an_earthbent_artifact_and_it_comes_back_untapped(cards):
    """616.1: Hardened Scales and Branching Evolution both apply to earthbend 4; Alice orders them (Scales first: 10). Beast Within destroys
    the earthbent Sol Ring: it returns tapped (701.66a), Amulet of Vigor untaps it, and it is a land entering (Tireless Provisioner)."""
    s = toph(cards, "Hardened Scales", "Branching Evolution", "Amulet of Vigor", "Tireless Provisioner", "Earthbending Lesson", "Beast Within")
    sol = put(s, "Sol Ring")
    for name in ("Hardened Scales", "Branching Evolution", "Amulet of Vigor", "Tireless Provisioner"):
        put(s, name)
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Earthbending Lesson").id, targets=[sol.id])
    asked = settle(s, "Hardened Scales first")
    assert any("(616.1)" in p for p in asked)
    assert counters(s, sol) == 10 and pt(s, sol) == (10, 10)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Beast Within").id, targets=[sol.id])
    settle(s, "Create a Food token")
    back = s.state.cards[sol.id]
    assert back.zone == "p1:battlefield" and not back.tapped and counters(s, back) == 0
    assert ch(s, back).types == {"Artifact", "Land"}  # a new object (400.7): not earthbent any more
    assert field(s)["Food"] == 1 and field(s)["Beast"] == 1
    check(s)


def test_artifact_lands_get_what_lands_get(cards):
    """Chromatic Lantern and Bootleggers' Stash give lands abilities: Sol Ring (a land under Toph) has both, and the Stash's Treasure ability
    is hinted and works."""
    s = toph(cards, "Chromatic Lantern", "Bootleggers' Stash")
    sol = put(s, "Sol Ring")
    put(s, "Chromatic Lantern")
    put(s, "Bootleggers' Stash")
    texts = [ab.text for ab in ch(s, sol).abilities]
    assert "{T}: Add one mana of any color." in texts and "{T}: Create a Treasure token." in texts
    stash = next(ab.index for ab in ch(s, sol).abilities if ab.text == "{T}: Create a Treasure token.")
    assert {"card_id": sol.id, "ability": stash} in hints(s.state, "p1", s.cards)["activatable"]
    act(s, "p1", type="activate_ability", card_id=sol.id, ability=stash)
    settle(s)
    assert field(s)["Treasure"] == 1 and s.state.cards[sol.id].tapped
    check(s)


def test_greatest_earthbender_and_blind_bandit_count_the_artifact_land(cards):
    """Toph, Greatest Earthbender cast for four mana earthbends 4 (Sol Ring: 4/4, double strike as a land creature); Toph, the Blind Bandit
    earthbends a Forest 2 and has power 6 (the +1/+1 counters on lands Alice controls)."""
    s = toph(cards, "Toph, Greatest Earthbender", "Toph, the Blind Bandit")
    sol = put(s, "Sol Ring")
    forest = put(s, "Forest")
    mana(s, R=1, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Toph, Greatest Earthbender").id)
    settle(s, "Sol Ring")
    assert pt(s, sol) == (4, 4) and {"double strike", "haste"} <= set(ch(s, sol).keywords)
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Toph, the Blind Bandit").id)
    settle(s, "Forest")
    assert counters(s, forest) == 2 and pt(s, card(s, "Toph, the Blind Bandit"))[0] == 6
    check(s)


def test_liquimetal_torque_turns_an_enchantment_into_an_artifact_land(cards):
    """613.8: Toph's land-making depends on Liquimetal Torque's (it changes what Toph applies to): Hardened Scales becomes an artifact, so a
    nontoken artifact Alice controls, so a land too, until end of turn."""
    s = toph(cards, "Liquimetal Torque", "Hardened Scales")
    torque = put(s, "Liquimetal Torque")
    scales = put(s, "Hardened Scales")
    ability = next(ab.index for ab in ch(s, torque).abilities if ab.text.startswith("{T}: Target nonland permanent"))
    act(s, "p1", type="activate_ability", card_id=torque.id, ability=ability, targets=[scales.id])
    settle(s)
    assert ch(s, scales).types == {"Artifact", "Enchantment", "Land"}
    check(s)


def test_an_artifact_cast_in_the_main_phase_gives_moraug_an_extra_combat(cards):
    """Moraug's landfall: Thought Vessel cast in Alice's first main phase is a land entering in her main phase: an additional combat phase.
    Ashaya counts the artifact lands and the nontoken creatures (Forest lands) too."""
    s = toph(cards, "Moraug, Fury of Akoum", "Thought Vessel", "Ashaya, Soul of the Wild", "Scute Swarm")
    put(s, "Moraug, Fury of Akoum")
    ashaya = put(s, "Ashaya, Soul of the Wild")
    put(s, "Sol Ring")
    assert pt(s, ashaya) == (4, 4)  # Toph, Moraug, Ashaya (creatures: Forest lands) and Sol Ring
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thought Vessel").id)
    settle(s)
    assert pt(s, ashaya) == (5, 5)
    assert any(e.parts and "additional combat phase" in "".join(p.t or "" for p in e.parts) for e in s.state.log[-6:])
    until(s, "p1", "main2")
    combats = [e for e in s.state.log if any((p.t or "").startswith("— Beginning of combat") for p in e.parts)]
    assert len(combats) == 2
    check(s)
