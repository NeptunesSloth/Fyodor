"""Wave 100A: triggered-ability lines the grammar didn't read (selectors, references, narrow exact wordings)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

# Real Oracle data (tests/fixtures/wave100a_cards.json, copied from the card database) plus a few plain probe cards.
REAL = json.loads((Path(__file__).parent / "fixtures" / "wave100a_cards.json").read_text())
EXTRA = [
    real("Probe Uneven", "{1}{G}", 2, "Creature — Beast", "", ("3", "1"), "G"),
    real("Probe Uneven Elf", "{1}{G}", 2, "Creature — Elf", "", ("1", "3"), "G"),
    real("Probe Curse", "{1}{B}", 2, "Enchantment — Aura Curse", "Enchant player\nAt the beginning of your upkeep, you draw a card.", None, "B"),
    real("Probe Duo", "{W}{U}", 2, "Creature — Human", "", ("2", "2"), "WU"),
    real("Probe Trio", "{W}{U}{B}", 3, "Creature — Human", "", ("2", "2"), "WUB"),
    real("Probe Walker", "{2}{U}", 3, "Legendary Planeswalker — Jace", "+1: Draw a card.", None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    real_cards = [card(c["name"], number=f"100A-{i}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(REAL)]
    build_database([*fixture_cards(), *EXTRA, *real_cards], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def run(s, pick=None, limit=40):
    """Resolve the stack; ``pick(decision)`` answers a decision (a list of option ids) or None for the first options."""
    seen = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers", "divide"):
            return seen
        if d is not None:
            seen.append(d)
            got = pick(d) if pick else None
            ids = got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return seen
    raise AssertionError("the stack never emptied")


def cast_it(s, name, pid="p1", pick=None, **m):
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id)
    return run(s, pick)


@pytest.mark.parametrize("name", ["Gilt-Leaf Winnower", "Witchbane Orb"])
def test_wave100a_selector_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_gilt_leaf_winnower_targets_only_unequal_non_elves(cards):
    s = build(cards, ["Gilt-Leaf Winnower"], ["Probe Uneven", "Probe Uneven Elf", "Grizzly Bears"])
    uneven, elf, bears = (put(s, n, "p2") for n in ("Probe Uneven", "Probe Uneven Elf", "Grizzly Bears"))
    offered = []

    def pick(d):
        ids = [o.id for o in d.options]
        if uneven.id in ids or bears.id in ids or elf.id in ids:
            offered.extend(ids)
            return [uneven.id]
        return ["yes"] if "yes" in ids else None

    cast_it(s, "Gilt-Leaf Winnower", pick=pick, B=2, C=3)
    assert uneven.id in offered and bears.id not in offered and elf.id not in offered  # 2/2 equal; the Elf excluded
    assert s.state.cards[uneven.id].zone == "p2:graveyard"
    assert s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def lib_card(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")


def cast_card(s, c, pid="p1", targets=(), pick=None, **m):
    mana(s, pid, **m)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    return run(s, pick)


def test_witchbane_orb_destroys_only_curses_attached_to_its_controller(cards):
    s = build(cards, ["Witchbane Orb", "Probe Curse", "Probe Curse"])
    on_me, on_bob = lib_card(s, "Probe Curse"), None
    cast_card(s, on_me, targets=["p1"], B=1, C=1)  # 303.4: a player Aura may enchant its own controller
    on_bob = lib_card(s, "Probe Curse")
    cast_card(s, on_bob, targets=["p2"], B=1, C=1)
    assert s.state.cards[on_me.id].attached_player == "p1" and s.state.cards[on_bob.id].attached_player == "p2"
    cast_it(s, "Witchbane Orb", C=4)
    assert s.state.cards[on_me.id].zone == "p1:graveyard"  # the Curse enchanting Alice
    assert s.state.cards[on_bob.id].zone == "p1:battlefield"  # Alice's own Curse on Bob stays
    assert card_named(s, "Witchbane Orb").zone == "p1:battlefield"
    check(s)


# -- selectors & native rewordings ---------------------------------------------------------------------------------------------------------
PROMOTED = ["Gilt-Leaf Winnower", "Witchbane Orb", "Invasion of Ravnica // Guildpact Paragon", "Invasion of Ulgrotha // Grandmother Ravi Sengir",
            "Invasion of Muraganda // Primordial Plasm", "Calculating Lich", "Lairwatch Giant"]


@pytest.mark.parametrize("name", PROMOTED)
def test_wave100a_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def offered_then(choice, offered):
    """A ``pick`` that records the options of the first decision offering ``choice`` and picks it (a confirm is answered yes)."""
    def pick(d):
        ids = [o.id for o in d.options]
        if choice in ids and not offered:
            offered.extend(ids)
            return [choice]
        return ["yes"] if "yes" in ids else None
    return pick


def test_invasion_of_ravnica_exiles_only_a_permanent_not_exactly_two_colors(cards):
    s = build(cards, ["Invasion of Ravnica // Guildpact Paragon"], ["Probe Duo", "Probe Trio", "Grizzly Bears"])
    duo, trio, bears = (put(s, n, "p2") for n in ("Probe Duo", "Probe Trio", "Grizzly Bears"))
    offered = []
    cast_it(s, "Invasion of Ravnica // Guildpact Paragon", pick=offered_then(trio.id, offered), C=5)
    assert trio.id in offered and bears.id in offered and duo.id not in offered  # three colors and one color are "not exactly two" (105.2)
    assert s.state.cards[trio.id].zone == "p2:exile" and s.state.cards[duo.id].zone == "p2:battlefield"
    check(s)


def test_invasion_of_ulgrotha_hits_any_target_but_itself_and_gains_life(cards):
    s = build(cards, ["Invasion of Ulgrotha // Grandmother Ravi Sengir"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    siege = card_named(s, "Invasion of Ulgrotha // Grandmother Ravi Sengir")
    offered = []
    cast_it(s, "Invasion of Ulgrotha // Grandmother Ravi Sengir", pick=offered_then("p2", offered), B=1, C=4)
    assert "p2" in offered and siege.id not in offered  # 115.4: "any other target" — not the Siege itself
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].life == 43
    check(s)


def test_primordial_plasm_pumps_and_strips_another_creature(cards):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase
    from tests.wave9c_kit import pt

    s = build(cards, ["Invasion of Muraganda // Primordial Plasm"], ["Kitchen Finks"])
    plasm = put(s, "Invasion of Muraganda // Primordial Plasm")
    act(s, "p1", type="set_face", card_id=plasm.id, face=1)
    finks = put(s, "Kitchen Finks", "p2")
    offered = []
    to_phase(s, "begin_combat", 1)
    run(s, offered_then(finks.id, offered))
    assert finks.id in offered and plasm.id not in offered  # "another target creature"
    assert pt(s, "Kitchen Finks", "p2") == (5, 4)
    finks_ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[finks.id])
    assert not finks_ch.abilities  # 613.1f: it lost all its abilities (persist with them)
    check(s)


def declare(s, turn, pairs):
    """Go to the declare attackers step of ``turn`` and attack with ``pairs`` (card, player id or permanent id)."""
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "declare_attackers", turn)
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers", d
    act(s, d.player, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def test_calculating_lich_each_attacked_opponent_loses_life(cards):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Calculating Lich", "Grizzly Bears"], ["Grizzly Bears", "Probe Walker"], ["Grizzly Bears"])
    lich, mine = put(s, "Calculating Lich"), put(s, "Grizzly Bears")
    bobs, carols = put(s, "Grizzly Bears", "p2"), put(s, "Grizzly Bears", "p3")
    walker = put(s, "Probe Walker", "p2")
    act(s, "p2", type="set_counter", card_id=walker.id, kind="loyalty", value=3)
    declare(s, 2, [(bobs, "p1")])  # Bob attacks Alice: not one of Alice's opponents
    run(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [40, 40, 40]
    declare(s, 3, [(carols, "p2")])  # Carol attacks Bob, one of Alice's opponents: 508.5, Bob is that creature's defending player
    run(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [38, 37, 40]  # (and the combat damage: 2 to Alice, 2 to Bob)
    declare(s, 4, [(lich, "p3"), (mine, walker.id)])  # one trigger per creature attacking an opponent; a planeswalker isn't the player (508.3a)
    run(s)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [38, 37, 34]  # (and the Lich's 5 combat damage to Carol)
    assert s.state.cards[walker.id].counters.get("loyalty") == 1
    check(s)


def test_lairwatch_giant_first_strike_only_when_blocking_two(cards):
    from app.rules.plan import Plan

    for both in (False, True):
        s = build(cards, ["Lairwatch Giant"], ["Grizzly Bears", "Kitchen Finks"])
        giant = put(s, "Lairwatch Giant")
        bears, finks = put(s, "Grizzly Bears", "p2"), put(s, "Kitchen Finks", "p2")
        declare(s, 2, [(bears, "p1"), (finks, "p1")])
        run(s)
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, "declare_blockers", 2)
        d = s.state.rules.decision
        assert d is not None and d.kind == "declare_blockers"
        blocks = [{"blocker_id": giant.id, "attacker_id": bears.id}] + ([{"blocker_id": giant.id, "attacker_id": finks.id}] if both else [])
        act(s, "p1", type="declare_blockers", blocks=blocks)
        run(s)
        ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[giant.id])
        assert ("first strike" in [k.lower() for k in ch.keywords]) is both  # 509.3e: it blocks two creatures as blockers are declared
        check(s)


PROMOTED += ["Kitesail Skirmisher", "Dinrova Horror", "Carrion Locust", "Spreading Plague"]


@pytest.mark.parametrize("name", ["Kitesail Skirmisher", "Dinrova Horror", "Carrion Locust", "Spreading Plague"])
def test_wave100a_promoted_cards_are_full_2(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_kitesail_skirmisher_only_a_creature_attacking_the_same_player(cards):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Kitesail Skirmisher", "Grizzly Bears", "Llanowar Elves"], [], [])
    kite, bears, elves = put(s, "Kitesail Skirmisher"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    offered = []
    declare(s, 4, [(kite, "p2"), (bears, "p2"), (elves, "p3")])
    run(s, offered_then(bears.id, offered))
    assert bears.id in offered and elves.id not in offered and kite.id not in offered  # Elves attack Carol; "another"
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    assert "flying" in plan.ch(s.state.cards[bears.id]).keywords and "flying" not in plan.ch(s.state.cards[elves.id]).keywords
    check(s)


@pytest.mark.parametrize("own", [False, True])
def test_dinrova_horror_the_owner_of_the_returned_permanent_discards(cards, own):
    s = build(cards, ["Dinrova Horror", "Grizzly Bears"], ["Grizzly Bears", "Island"])
    victim = put(s, "Grizzly Bears", "p1" if own else "p2")
    owner = "p1" if own else "p2"
    if not own:
        act(s, "p2", type="move", card_ids=[card_named(s, "Island", "p2").id], to={"zone": "hand"})
    picks = []

    def pick(d):
        ids = [o.id for o in d.options]
        if victim.id in ids and not picks:
            picks.append("target")
            return [victim.id]
        if d.player == owner and d.kind != "order":
            picks.append(d.player)
        return None

    cast_it(s, "Dinrova Horror", pick=pick, U=1, B=1, C=4)
    hand = s.state.zones.get(f"{owner}:hand", [])
    graveyard = s.state.zones.get(f"{owner}:graveyard", [])
    assert len(graveyard) == 1 and victim.id in hand + graveyard  # back to its owner's hand, then that player discarded one card
    if not own:
        assert s.state.zones.get("p1:graveyard", []) == []  # Alice discarded nothing
    check(s)


@pytest.mark.parametrize("creature", [True, False])
def test_carrion_locust_life_loss_only_for_a_creature_card(cards, creature):
    s = build(cards, ["Carrion Locust"], ["Grizzly Bears", "Island"])
    gone = card_named(s, "Grizzly Bears" if creature else "Island", "p2")
    act(s, "p2", type="move", card_ids=[gone.id], to={"zone": "graveyard"})
    cast_it(s, "Carrion Locust", pick=offered_then(gone.id, []), B=2, C=2)
    assert s.state.cards[gone.id].zone == "p2:exile"
    assert s.state.players["p2"].life == (39 if creature else 40)
    check(s)


def test_spreading_plague_destroys_others_sharing_a_color_without_regeneration(cards):
    s = build(cards, ["Spreading Plague", "Llanowar Elves", "Frogmite"], ["Grizzly Bears", "Probe Duo", "Albino Troll"])
    plague = put(s, "Spreading Plague")
    bears, duo, troll = put(s, "Grizzly Bears", "p2"), put(s, "Probe Duo", "p2"), put(s, "Albino Troll", "p2")
    cast_it(s, "Frogmite", C=4)  # colorless: shares no color (105.2c)
    assert [s.state.cards[c.id].zone for c in (bears, duo, troll)] == ["p2:battlefield"] * 3
    elves = card_named(s, "Llanowar Elves")
    act(s, "p2", type="set_prefs", response="on")  # Bob is asked to respond
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)
    shielded = False
    for _ in range(20):  # with the Plague's trigger on the stack, Bob regenerates the Troll first (701.19c: the shield can't be used)
        if s.state.rules.decision is not None:
            run(s)
        elif not s.state.zones.get("stack"):
            break
        elif s.state.rules.priority == "p2" and not shielded and s.state.cards[elves.id].zone == "p1:battlefield":
            mana(s, "p2", C=1, G=1)
            act(s, "p2", type="activate_ability", card_id=troll.id, ability=1)
            shielded = True
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert shielded
    elves = card_named(s, "Llanowar Elves")
    assert s.state.cards[elves.id].zone == "p1:battlefield"  # "other": not the entering creature
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[troll.id].zone == "p2:graveyard"
    assert s.state.cards[duo.id].zone == "p2:battlefield" and s.state.cards[plague.id].zone == "p1:battlefield"
    check(s)


# -- returns, hand exile, permanent goad ----------------------------------------------------------------------------------------------------
BATCH2 = ["Saltskitter", "Ghastlord of Fugue", "Nettling Nuisance"]
PROMOTED += BATCH2


@pytest.mark.parametrize("name", BATCH2)
def test_wave100a_batch2_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_saltskitter_blinks_until_the_next_end_step_when_another_creature_enters(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Saltskitter", "Grizzly Bears"], ["Llanowar Elves"])
    salt = put(s, "Saltskitter")
    cast_it(s, "Grizzly Bears", G=1, C=1)
    assert s.state.cards[salt.id].zone == "p1:exile"
    old = s.state.rules.object_id(salt.id)
    to_phase(s, "main1", 2)  # it came back at the beginning of turn 1's end step
    assert s.state.cards[salt.id].zone == "p1:battlefield" and s.state.rules.object_id(salt.id) != old  # 400.7: a new object
    cast_it(s, "Llanowar Elves", "p2", G=1)  # an opponent's creature is "another creature" too
    assert s.state.cards[salt.id].zone == "p1:exile"
    check(s)


def test_ghastlord_of_fugue_exiles_the_card_its_controller_picks_from_the_revealed_hand(cards):
    s = build(cards, ["Ghastlord of Fugue"], ["Lightning Bolt", "Counterspell"])
    ghast = put(s, "Ghastlord of Fugue")
    bolt, spell = card_named(s, "Lightning Bolt", "p2"), card_named(s, "Counterspell", "p2")
    act(s, "p2", type="move", card_ids=[bolt.id, spell.id], to={"zone": "hand"})
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if spell.id in ids:
            asked.append((d.player, set(ids)))
            return [spell.id]
        return None

    declare(s, 3, [(ghast, "p2")])
    run(s, pick)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main2", 3)
    assert asked and asked[0][0] == "p1" and {bolt.id, spell.id} <= asked[0][1]  # Alice chooses among the revealed cards
    assert s.state.cards[spell.id].zone == "p2:exile" and s.state.cards[bolt.id].zone == "p2:hand"
    check(s)


def test_nettling_nuisance_gives_the_damaged_player_a_pirate_goaded_for_the_rest_of_the_game(cards):
    from app.game.errors import ActionError
    from app.rules.keyword_actions import goaded_by
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Nettling Nuisance"], [])
    fae = put(s, "Nettling Nuisance")
    declare(s, 3, [(fae, "p2")])
    to_phase(s, "main2", 3)
    pirates = [c for c in s.state.cards.values() if c.name == "Pirate" and c.zone == "p2:battlefield"]
    assert len(pirates) == 1 and pirates[0].controller == "p2"
    pirate = pirates[0]
    declare(s, 4, [(pirate, "p1")])
    to_phase(s, "main1", 5)  # Alice's next turn began: an ordinary goad (701.15a) would end here; this one lasts the rest of the game
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[pirate.id])
    assert goaded_by(ch) == {"p1"}  # goaded by the ability's controller (701.15a)
    to_phase(s, "declare_attackers", 6)
    with pytest.raises(ActionError, match="goaded"):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": pirate.id, "target": "p1"}])
    check(s)


BATCH3 = ["Kav Landseeker", "Mutable Explorer", "Patient Naturalist", "Soul of Emancipation", "Dream Eater", "Azor, the Lawbringer", "Sphinx's Decree"]
PROMOTED += BATCH3
EXTRA += [real("Probe Wall", "{2}", 2, "Artifact", "Indestructible"), real("Probe Wall Creature", "{1}{U}", 2, "Creature — Wall", "Defender", ("0", "4"), "U")]


@pytest.mark.parametrize("name", BATCH3)
def test_wave100a_batch3_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_kav_landseeker_sacrifices_the_lander_at_the_end_step_of_your_next_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Kav Landseeker"])
    act(s, "p1", type="set_stops", own=["end"], others=["end"], smart_pass=False)
    cast_it(s, "Kav Landseeker", R=1, C=3)
    lander = next(c for c in s.state.cards.values() if c.name == "Lander")
    for turn in (1, 2):  # not this turn's end step (Alice's), nor Bob's
        to_phase(s, "end", turn)
        run(s)
        assert s.state.cards[lander.id].zone == "p1:battlefield"
    to_phase(s, "end", 3)
    run(s)
    assert lander.id not in s.state.cards or not s.state.cards[lander.id].zone.endswith(":battlefield")
    check(s)


def test_mutable_explorer_makes_a_tapped_mutavault_that_animates(cards):
    from app.rules.plan import Plan

    s = build(cards, ["Mutable Explorer"])
    cast_it(s, "Mutable Explorer", G=1, C=2)
    vault = next(c for c in s.state.cards.values() if c.name == "Mutavault")
    plan = Plan(s.state, "p1", s.cards, None)
    ch = plan.ch(vault)
    assert vault.tapped and vault.is_token and ch.types == {"Land"} and not ch.is_creature and vault.controller == "p1"
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
    run(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[vault.id])
    assert ch.is_creature and "Land" in ch.types and ch.pt == (2, 2) and {"Elf", "Shapeshifter", "Goblin"} <= ch.subtypes
    check(s)


@pytest.mark.parametrize("lands", [0, 1, 2])
def test_patient_naturalist_puts_a_milled_land_into_hand_or_makes_a_treasure(cards, lands):
    s = build(cards, ["Patient Naturalist", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    others = [card_named(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt")]
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:lands]
    top = [*forests, *others][:3]
    for c in reversed(top):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    asked = []

    def pick(d):
        if d.kind == "choose_cards":
            asked.append((d.min_choices, d.max_choices, [o.id for o in d.options]))
        return None

    cast_it(s, "Patient Naturalist", pick=pick, G=1, C=2)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    in_hand = [c for c in forests if s.state.cards[c.id].zone == "p1:hand"]
    assert len(treasures) == (1 if lands == 0 else 0) and len(in_hand) == min(lands, 1)
    if lands == 2:  # not optional: one of them must be taken (min 1)
        assert asked and asked[0][:2] == (1, 1) and set(asked[0][2]) == {f.id for f in forests}
    check(s)


def test_soul_of_emancipation_one_angel_per_legal_target_for_its_controller(cards):
    s = build(cards, ["Soul of Emancipation", "Llanowar Elves"], ["Grizzly Bears", "Probe Wall"])
    elves = put(s, "Llanowar Elves")
    bears, wall = put(s, "Grizzly Bears", "p2"), put(s, "Probe Wall", "p2")

    def pick(d):
        ids = [o.id for o in d.options]
        if bears.id in ids:
            return [bears.id, wall.id, elves.id]
        return None

    cast_it(s, "Soul of Emancipation", pick=pick, W=2, G=1, U=1, C=3)
    angels = {p: sum(1 for c in s.state.cards.values() if c.name == "Angel" and c.zone == f"{p}:battlefield") for p in ("p1", "p2")}
    assert angels == {"p1": 1, "p2": 2}  # the indestructible one wasn't destroyed: its controller still gets an Angel (the official ruling)
    assert s.state.cards[wall.id].zone == "p2:battlefield" and s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    check(s)


def test_dream_eater_targets_after_the_surveil(cards):
    s = build(cards, ["Dream Eater"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    order = []

    def pick(d):
        ids = [o.id for o in d.options]
        if bears.id in ids:
            order.append("target")
            return [bears.id]
        order.append(d.kind)
        return ["yes"] if "yes" in ids else None

    cast_it(s, "Dream Eater", pick=pick, U=2, C=4)
    assert "target" in order and order.index("target") > 0  # the surveil came first (603.12: the target is chosen once it has happened)
    assert s.state.cards[bears.id].zone == "p2:hand"
    check(s)


def test_sphinxs_decree_each_opponent_only_during_their_own_next_turn(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import three, to_phase

    s = three(cards, ["Sphinx's Decree"], ["Lightning Bolt", "Opt"], ["Lightning Bolt"])
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Sphinx's Decree").id)
    run(s)
    for pid in ("p2", "p3"):
        act(s, pid, type="move", card_ids=[card_named(s, "Lightning Bolt", pid).id], to={"zone": "hand"})
    act(s, "p2", type="move", card_ids=[card_named(s, "Opt", "p2").id], to={"zone": "hand"})
    to_phase(s, "main1", 2)
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=["p1"])
    to_phase(s, "main1", 3)
    mana(s, "p3", R=1)
    with pytest.raises(ActionError):
        act(s, "p3", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p3").id, targets=["p1"])
    to_phase(s, "main1", 5)  # Bob's next turn is over: he casts again
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Opt", "p2").id)
    run(s)
    assert card_named(s, "Opt", "p2").zone == "p2:graveyard"
    check(s)


def test_azor_limits_each_opponent_on_their_next_turn(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Azor, the Lawbringer"], ["Lightning Bolt", "Opt"])
    cast_it(s, "Azor, the Lawbringer", W=2, U=2, C=2)
    for name in ("Lightning Bolt", "Opt"):
        act(s, "p2", type="move", card_ids=[card_named(s, name, "p2").id], to={"zone": "hand"})
    to_phase(s, "main1", 2)
    mana(s, "p2", U=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Opt", "p2").id)
    to_phase(s, "main1", 4)
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Opt", "p2").id)
    run(s)
    assert card_named(s, "Opt", "p2").zone == "p2:graveyard"
    check(s)


# -- batch 4: optional lands, block requirements, upkeep costs, "until your next upkeep" -----------------------------------------------------
BATCH4 = ["Graceful Antelope", "Crashing Boars", "Gravestorm", "Egon, God of Death // Throne of Death", "Anurid Scavenger", "Chisei, Heart of Oceans",
          "Gabriel Angelfire", "Erhnam Djinn"]
PROMOTED += BATCH4


@pytest.mark.parametrize("name", BATCH4)
def test_wave100a_batch4_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def stops(s, *steps):
    """Alice is given priority in these steps of every turn (an upkeep trigger that asks nothing would otherwise pass unseen)."""
    act(s, "p1", type="set_stops", own=list(steps), others=list(steps), smart_pass=False)


def _ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("accept", [True, False])
def test_graceful_antelope_makes_a_land_a_plains_while_it_remains(cards, accept):
    s = build(cards, ["Graceful Antelope", "Murder"])
    ante = put(s, "Graceful Antelope")
    island = put(s, "Island", "p2")
    declare(s, 3, [(ante, "p2")])

    def pick(d):
        ids = [o.id for o in d.options]
        if island.id in ids:
            return [island.id]
        if "yes" in ids:
            return ["yes" if accept else "no"]
        return None

    run(s, pick)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main2", 3)
    assert _ch(s, island).subtypes == ({"Plains"} if accept else {"Island"})  # 305.7: it's only a Plains
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[ante.id])
    run(s)
    assert s.state.cards[ante.id].zone == "p1:graveyard"
    assert _ch(s, island).subtypes == {"Island"}  # 611.2b: the Antelope left the battlefield
    check(s)


def test_crashing_boars_the_chosen_untapped_creature_must_block_it(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Crashing Boars"], ["Grizzly Bears", "Llanowar Elves", "Kitchen Finks"])
    boars = put(s, "Crashing Boars")
    bears, elves, finks = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Kitchen Finks", "p2")
    to_phase(s, "main1", 3)
    act(s, "p2", type="tap", card_ids=[finks.id])
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if elves.id in ids:
            asked.append((d.player, set(ids)))
            return [elves.id]
        return None

    declare(s, 3, [(boars, "p2")])
    run(s, pick)
    assert asked == [("p2", {bears.id, elves.id})]  # Bob chooses, among his untapped creatures
    to_phase(s, "declare_blockers", 3)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": boars.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": boars.id}])
    run(s)
    assert s.state.players["p2"].life == 40 and s.state.cards[boars.id].damage == 1  # blocked by the Elves
    check(s)


@pytest.mark.parametrize("case", ["exiles", "declines", "empty"])
def test_gravestorm_you_may_draw_when_the_opponent_does_not_exile(cards, case):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Gravestorm"], ["Grizzly Bears"])
    put(s, "Gravestorm")
    bears = card_named(s, "Grizzly Bears", "p2")
    if case != "empty":
        act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    stops(s, "upkeep", "main1")
    to_phase(s, "upkeep", 3)
    hand = len(s.state.zones.get("p1:hand", []))

    def pick(d):
        ids = [o.id for o in d.options]
        if d.player == "p2" and "pay" in ids:
            return ["pay" if case == "exiles" else "decline"]
        if d.player == "p2" and bears.id in ids:
            return [bears.id]
        if d.player == "p1" and "yes" in ids:
            return ["yes"]
        return None

    run(s, pick)
    to_phase(s, "main1", 3)
    drew = len(s.state.zones.get("p1:hand", [])) - hand - 1  # (and the draw step's card)
    assert drew == (0 if case == "exiles" else 1)
    if case == "exiles":
        assert s.state.cards[bears.id].zone == "p2:exile"
    check(s)


@pytest.mark.parametrize("cards_in_yard", [3, 2, 1])
def test_egon_exiles_two_or_is_sacrificed_for_a_card(cards, cards_in_yard):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Egon, God of Death // Throne of Death", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    egon = put(s, "Egon, God of Death // Throne of Death")
    yard = [card_named(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt")][:cards_in_yard]
    act(s, "p1", type="move", card_ids=[c.id for c in yard], to={"zone": "graveyard"})
    asked = []

    def pick(d):
        if d.kind == "choose_cards" and d.player == "p1":
            asked.append((d.min_choices, d.max_choices))
            return [o.id for o in d.options][:2]
        return None

    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s, pick)
    exiled = [c for c in yard if s.state.cards[c.id].zone == "p1:exile"]
    if cards_in_yard >= 2:
        assert len(exiled) == 2 and s.state.cards[egon.id].zone == "p1:battlefield"  # no choice to decline (the official ruling)
        assert asked == ([(2, 2)] if cards_in_yard == 3 else [])
    else:
        assert not exiled and s.state.cards[egon.id].zone == "p1:graveyard"  # one card isn't exiled: sacrificed, and a card drawn
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_anurid_scavenger_puts_a_card_on_the_bottom_or_is_sacrificed(cards, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Anurid Scavenger", "Grizzly Bears"])
    scav = put(s, "Anurid Scavenger")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s, lambda d: ([bears.id] if pay else []) if d.kind == "choose_cards" else None)
    if pay:
        assert s.state.zones["p1:library"][-1] == bears.id and s.state.cards[scav.id].zone == "p1:battlefield"
    else:
        assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[scav.id].zone == "p1:graveyard"
    check(s)


def test_anurid_scavenger_with_an_empty_graveyard_is_sacrificed(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Anurid Scavenger"])
    scav = put(s, "Anurid Scavenger")
    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s)
    assert s.state.cards[scav.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_chisei_removes_a_counter_from_any_permanent_you_control_or_is_sacrificed(cards, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Chisei, Heart of Oceans", "Grizzly Bears"], ["Llanowar Elves"])
    chisei, bears = put(s, "Chisei, Heart of Oceans"), put(s, "Grizzly Bears")
    elves = put(s, "Llanowar Elves", "p2")
    act(s, "p1", type="set_counter", card_id=bears.id, kind="+1/+1", value=2)
    act(s, "p2", type="set_counter", card_id=elves.id, kind="+1/+1", value=1)
    offered = []

    def pick(d):
        if d.kind == "choose_cards":
            offered.extend(o.card_id for o in d.options)
            return [d.options[0].id] if pay else []
        return None

    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s, pick)
    assert set(offered) == {bears.id}  # only permanents Alice controls
    assert s.state.cards[bears.id].counters.get("+1/+1") == (1 if pay else 2)
    assert s.state.cards[chisei.id].zone == ("p1:battlefield" if pay else "p1:graveyard")
    check(s)


def test_erhnam_djinn_forestwalk_lasts_until_your_next_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Erhnam Djinn"], ["Grizzly Bears", "Probe Wall Creature"])
    put(s, "Erhnam Djinn")
    bears, wall = put(s, "Grizzly Bears", "p2"), put(s, "Probe Wall Creature", "p2")
    stops(s, "upkeep", "main1")
    to_phase(s, "upkeep", 3)
    offered = []
    run(s, offered_then(bears.id, offered))
    assert bears.id in offered and wall.id not in offered  # "non-Wall"
    assert "forestwalk" in _ch(s, bears).keywords
    to_phase(s, "main1", 4)  # through Bob's turn
    assert "forestwalk" in _ch(s, bears).keywords
    to_phase(s, "upkeep", 5)  # ends as Alice's next upkeep begins (611.2a)
    assert "forestwalk" not in _ch(s, bears).keywords
    check(s)


def test_gabriel_angelfire_keeps_its_choice_until_your_next_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Gabriel Angelfire"], ["Grizzly Bears", "Llanowar Elves"])
    gab = put(s, "Gabriel Angelfire")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    stops(s, "upkeep", "main1")
    to_phase(s, "upkeep", 3)
    run(s, lambda d: [next(o.id for o in d.options if o.label == "Trample")] if any(o.label == "Trample" for o in d.options) else None)
    assert "trample" in _ch(s, gab).keywords
    to_phase(s, "main1", 4)
    assert "trample" in _ch(s, gab).keywords
    to_phase(s, "upkeep", 5)
    assert "trample" not in _ch(s, gab).keywords  # the official ruling: not during the next upkeep
    run(s, lambda d: [next(o.id for o in d.options if o.label == "Rampage 3")] if any(o.label == "Rampage 3" for o in d.options) else None)
    assert any(a.text.rstrip(".") == "Rampage 3" for a in _ch(s, gab).abilities)  # the granted keyword line (613.1f), beside the printed trigger
    declare(s, 5, [(gab, "p2")])
    run(s)
    to_phase(s, "declare_blockers", 5)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": gab.id} for b in (bears, elves)])
    run(s)  # 702.23a: rampage 3, blocked by two: +3/+3 for the one beyond the first
    from tests.wave9c_kit import pt

    assert pt(s, "Gabriel Angelfire") == (7, 7)
    check(s)


def test_xenic_poltergeist_animation_wears_off_at_your_next_upkeep(cards):
    """"Until your next upkeep" (delayed.DURATIONS) on an activated ability: the official ruling — it wears off at the beginning of the upkeep."""
    from tests.test_rules_wave30m_durations import to_phase
    from tests.wave9c_kit import pt

    assert coverage.of_card_data(cards.resolve("Xenic Poltergeist")).level == "FULL"
    s = build(cards, ["Xenic Poltergeist", "Sol Ring"])
    ghost, ring = put(s, "Xenic Poltergeist"), put(s, "Sol Ring")
    stops(s, "upkeep", "main1")
    to_phase(s, "main1", 3)
    act(s, "p1", type="activate_ability", card_id=ghost.id, ability=0, targets=[ring.id])
    run(s)
    assert _ch(s, ring).is_creature and pt(s, "Sol Ring") == (1, 1)  # its mana value
    to_phase(s, "main1", 4)
    assert _ch(s, ring).is_creature
    to_phase(s, "upkeep", 5)
    assert not _ch(s, ring).is_creature
    check(s)
