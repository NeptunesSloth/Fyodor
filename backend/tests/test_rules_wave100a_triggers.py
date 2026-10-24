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




# -- batch 5: control to the damaging side, per-player attack pumps, linked players ----------------------------------------------------------
BATCH5 = ["Contested War Zone", "Contested Game Ball", "Indentured Djinn", "Jurin, Leading the Charge", "Namor, Atlantean King",
          "Mirkwood Trapper", "Soul Scourge", "Laquatus's Champion"]
PROMOTED += BATCH5


@pytest.mark.parametrize("name", BATCH5)
def test_wave100a_batch5_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_contested_war_zone_goes_to_whoever_damages_its_controller(cards):
    s = build(cards, ["Contested War Zone", "Grizzly Bears"], ["Grizzly Bears"])
    zone, mine = put(s, "Contested War Zone"), put(s, "Grizzly Bears")
    bobs = put(s, "Grizzly Bears", "p2")
    declare(s, 2, [(bobs, "p1")])
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main2", 2)
    assert s.state.cards[zone.id].controller == "p2"  # "that creature's controller"
    declare(s, 3, [(mine, "p2")])  # now Bob is "you" (the official ruling: its current controller)
    to_phase(s, "main2", 3)
    assert s.state.cards[zone.id].controller == "p1"
    check(s)


def test_contested_game_ball_one_trigger_for_simultaneous_damage_and_untapped(cards):
    s = build(cards, ["Contested Game Ball"], ["Grizzly Bears", "Llanowar Elves"])
    ball = put(s, "Contested Game Ball")
    act(s, "p1", type="tap", card_ids=[ball.id], tapped=True)
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    declare(s, 2, [(bears, "p1"), (elves, "p1")])
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main2", 2)
    assert s.state.cards[ball.id].controller == "p2" and not s.state.cards[ball.id].tapped  # the attacking player, untapped
    stacked = [x for x in s.state.log if "Contested Game Ball’s ability" in "".join(p.t or "" for p in x.parts) and "put an ability on the stack" in "".join(p.t or "" for p in x.parts)]
    assert len(stacked) == 1  # the official ruling: once, however many creatures dealt the damage
    check(s)


def test_indentured_djinn_each_other_player_chooses_how_many_to_draw(cards):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Indentured Djinn"], [], [])
    hands = {p: len(s.state.zones.get(f"{p}:hand", [])) for p in ("p2", "p3")}
    asked = []

    def pick(d):
        if d.player in ("p2", "p3") and {"0", "3"} <= {o.id for o in d.options}:
            asked.append(d.player)
            return ["2" if d.player == "p2" else "0"]
        return None

    cast_it(s, "Indentured Djinn", pick=pick, U=2, C=1)
    assert asked == ["p2", "p3"]  # APNAP: Bob, then Carol (101.4); Alice isn't asked
    assert {p: len(s.state.zones.get(f"{p}:hand", [])) - hands[p] for p in ("p2", "p3")} == {"p2": 2, "p3": 0}
    check(s)


def test_jurin_pumps_each_attacker_by_its_defending_players_creatures(cards):
    from tests.test_rules_wave30m_durations import three, to_phase
    from tests.wave9c_kit import pt

    s = three(cards, ["Jurin, Leading the Charge", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Llanowar Elves", "Probe Walker"], ["Grizzly Bears"])
    jurin, bears, elves = put(s, "Jurin, Leading the Charge"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = [put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Grizzly Bears", "p3")]
    walker = put(s, "Probe Walker", "p2")
    act(s, "p2", type="set_counter", card_id=walker.id, kind="loyalty", value=5)
    to_phase(s, "main1", 4)
    for c in theirs:
        act(s, c.controller, type="tap", card_ids=[c.id], tapped=True)  # (none can block: Jurin's block requirement asks nothing)
    declare(s, 4, [(jurin, "p2"), (bears, "p3"), (elves, walker.id)])
    run(s)
    assert pt(s, "Jurin, Leading the Charge") == (6, 6)  # Bob controls two creatures
    assert pt(s, "Grizzly Bears") == (3, 2)  # Carol controls one
    assert pt(s, "Llanowar Elves") == (1, 1)  # attacking a planeswalker, not a player
    check(s)


@pytest.mark.parametrize("richer", [True, False])
def test_namor_pumps_the_others_attacking_a_player_with_more_life(cards, richer):
    from tests.test_rules_wave30m_durations import three
    from tests.wave9c_kit import pt

    s = three(cards, ["Namor, Atlantean King", "Grizzly Bears", "Llanowar Elves"], [], [])
    namor, bears, elves = put(s, "Namor, Atlantean King"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p2", type="set_life", player="p2", value=41 if richer else 40)
    declare(s, 4, [(namor, "p2"), (bears, "p2"), (elves, "p3")])
    run(s)
    assert pt(s, "Grizzly Bears") == ((4, 2) if richer else (2, 2))
    assert pt(s, "Llanowar Elves") == (1, 1) and pt(s, "Namor, Atlantean King") == (2, 2)  # attacking another player; "other"
    check(s)


@pytest.mark.parametrize("at", ["p3", "p1", "walker"])
def test_mirkwood_trapper_attacker_chooses_a_pumped_attacker_when_not_attacking_you(cards, at):
    """Not when a creature attacks Alice; attacking only her planeswalker still counts as not attacking her (the official ruling)."""
    from tests.test_rules_wave30m_durations import three
    from tests.wave9c_kit import pt

    s = three(cards, ["Mirkwood Trapper", "Probe Walker"], ["Grizzly Bears", "Llanowar Elves"], [])
    put(s, "Mirkwood Trapper")
    walker = put(s, "Probe Walker")
    act(s, "p1", type="set_counter", card_id=walker.id, kind="loyalty", value=5)
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if d.player == "p2" and bears.id in ids:
            asked.append(set(ids))
            return [bears.id]
        if d.player == "p1" and bears.id in ids:
            return [elves.id]  # (its other trigger: "target attacking creature gets -2/-0")
        return None

    declare(s, 2, [(bears, "p3"), (elves, walker.id if at == "walker" else at)])
    run(s, pick)
    if at == "p1":
        assert not asked and pt(s, "Grizzly Bears", "p2") == (2, 2)
    else:
        assert asked == [{bears.id, elves.id}] and pt(s, "Grizzly Bears", "p2") == (4, 2)
    check(s)


@pytest.mark.parametrize("name,n", [("Soul Scourge", 3), ("Laquatus's Champion", 6)])
def test_linked_player_gains_back_the_life_when_it_leaves(cards, name, n):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, [name, "Murder"], [], [])
    cast_it(s, name, pick=lambda d: ["p3"] if "p3" in [o.id for o in d.options] else None, B=2, C=4)
    assert s.state.players["p3"].life == 40 - n
    act(s, "p1", type="move", card_ids=[card_named(s, "Murder").id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, name).id])
    run(s)
    assert s.state.players["p3"].life == 40 and s.state.players["p2"].life == 40  # "that player": the one its first ability targeted
    check(s)


def test_linked_player_still_on_the_stack(cards):
    """The official ruling (Laquatus's Champion): if the first ability is still on the stack, the player gaining is its target."""
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Soul Scourge", "Murder"], [], [])
    scourge = card_named(s, "Soul Scourge")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, B=3, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Soul Scourge").id)
    act(s, "p1", type="move", card_ids=[card_named(s, "Murder").id], to={"zone": "hand"})
    killed = False
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        elif not s.state.zones.get("stack"):
            break
        elif not killed and s.state.cards[scourge.id].zone == "p1:battlefield" and s.state.rules.priority == "p1" and len(s.state.zones["stack"]) == 1:
            act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[scourge.id])  # in response to its enters ability
            killed = True
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert killed and s.state.cards[scourge.id].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 40  # gained 3 (the leaves ability resolved first), then lost 3
    check(s)


def test_linked_player_twice_targeted_is_resolved_by_hand(cards):
    """Its enters ability triggered twice (Panharmonicon) and targeted two players: no ruling says who "that player" is, so it's manual."""
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Soul Scourge", "Panharmonicon", "Murder"], [], [])
    put(s, "Panharmonicon")
    targets = iter(["p2", "p3"])
    cast_it(s, "Soul Scourge", pick=lambda d: [next(targets)] if "p3" in [o.id for o in d.options] else None, B=2, C=4)
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 37
    act(s, "p1", type="move", card_ids=[card_named(s, "Murder").id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, "Soul Scourge").id])
    seen = run(s)
    assert [d.kind for d in seen] == ["manual_resolution"] and "Bob, Carol" in seen[0].prompt
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 37  # nobody gains automatically
    check(s)


# -- batch 6: one trigger for every opponent, counters history, "may … if they don't", top creature card, devour tokens ------------------------
BATCH6 = ["Master of Barbs", "Mindblade Render", "Iridescent Hornbeetle", "Star Athlete", "Ogre Marauder", "Barrow Ghoul", "Cloaked Cadet",
          "Tenuous Truce", "Day of the Dragons", "Magmatic Galleon", "Clandestine Meddler"]
PROMOTED += BATCH6
EXTRA += [real("Probe Ping", "{R}", 1, "Sorcery", "Probe Ping deals 1 damage to each opponent.", None, "R"),
          real("Probe Warrior", "{1}{R}", 2, "Creature — Human Warrior", "", ("2", "2"), "R"),
          real("Probe Human", "{W}", 1, "Creature — Human", "", ("1", "1"), "W"),
          real("Probe Counters", "{G}", 1, "Sorcery", "Put a +1/+1 counter on each creature you control.", None, "G")]


@pytest.mark.parametrize("name", BATCH6)
def test_wave100a_batch6_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_master_of_barbs_one_pump_for_noncombat_damage_to_several_opponents(cards):
    from tests.test_rules_wave30m_durations import three, to_phase
    from tests.wave9c_kit import pt

    s = three(cards, ["Master of Barbs", "Probe Ping"], [], [])
    put(s, "Master of Barbs")
    to_phase(s, "main1", 4)
    cast_it(s, "Probe Ping", R=1)
    assert s.state.players["p2"].life == 39 and s.state.players["p3"].life == 39
    assert pt(s, "Master of Barbs") == (3, 1)  # once for the batch (603.2c), not once per opponent
    check(s)


def test_mindblade_render_once_when_a_warrior_dealt_some_of_the_combat_damage(cards):
    from tests.test_rules_wave30m_durations import three, to_phase

    s = three(cards, ["Mindblade Render", "Grizzly Bears", "Probe Warrior"], [], [])
    put(s, "Mindblade Render")
    bears, warrior = put(s, "Grizzly Bears"), put(s, "Probe Warrior")
    hand = len(s.state.zones["p1:hand"])
    declare(s, 4, [(bears, "p2")])  # the Bears are no Warrior: nothing (an intervening "if", 603.4)
    to_phase(s, "main2", 4)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and s.state.players["p1"].life == 40  # (its draw step)
    declare(s, 7, [(bears, "p2"), (warrior, "p3")])
    to_phase(s, "main2", 7)
    assert len(s.state.zones["p1:hand"]) == hand + 3 and s.state.players["p1"].life == 39  # once for both opponents (the ruling)
    check(s)


def test_iridescent_hornbeetle_counts_the_counters_you_put_on_your_creatures_this_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Iridescent Hornbeetle", "Grizzly Bears", "Probe Counters"], ["Grizzly Bears", "Probe Counters"])
    put(s, "Iridescent Hornbeetle"), put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    stops(s, "end")
    to_phase(s, "main1", 2)
    cast_it(s, "Probe Counters", "p2", G=1)  # Bob's counters on Bob's creature: not "you've put"
    to_phase(s, "main1", 3)
    cast_it(s, "Probe Counters", G=1)  # two counters, one on each of Alice's creatures
    to_phase(s, "end", 3)
    run(s)
    assert len([c for c in s.state.cards.values() if c.name == "Insect" and c.zone == "p1:battlefield"]) == 2
    check(s)


@pytest.mark.parametrize("sacrifice", [True, False])
def test_star_athlete_its_controller_sacrifices_or_takes_five(cards, sacrifice):
    s = build(cards, ["Star Athlete"], ["Sol Ring"])
    athlete, ring = put(s, "Star Athlete"), put(s, "Sol Ring", "p2")
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if ring.id in ids:
            return [ring.id]
        if d.player == "p2" and "pay" in ids:
            asked.append(d.player)
            return ["pay" if sacrifice else "decline"]
        return None

    declare(s, 3, [(athlete, "p2")])
    run(s, pick)
    assert asked == ["p2"]
    assert (s.state.cards[ring.id].zone == "p2:graveyard") == sacrifice
    assert s.state.players["p2"].life == 40 - 3 - (0 if sacrifice else 5)  # (and its 3 combat damage)
    check(s)


@pytest.mark.parametrize("sacrifice", [True, False])
def test_ogre_marauder_unblockable_unless_defending_player_sacrifices(cards, sacrifice):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Ogre Marauder"], ["Grizzly Bears", "Llanowar Elves"])
    ogre = put(s, "Ogre Marauder")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")

    def pick(d):
        ids = [o.id for o in d.options]
        if d.player == "p2" and "pay" in ids:
            return ["pay" if sacrifice else "decline"]
        if d.player == "p2" and elves.id in ids:
            return [elves.id]
        return None

    declare(s, 3, [(ogre, "p2")])
    run(s, pick)
    to_phase(s, "declare_blockers", 3)
    if sacrifice:
        assert s.state.cards[elves.id].zone == "p2:graveyard"
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": ogre.id}])
    else:
        from app.game.errors import ActionError

        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": ogre.id}])
    check(s)


@pytest.mark.parametrize("exile", [True, False])
def test_barrow_ghoul_exiles_only_the_top_creature_card(cards, exile):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Barrow Ghoul", "Grizzly Bears", "Llanowar Elves", "Sol Ring"])
    ghoul = put(s, "Barrow Ghoul")
    bears, elves, ring = card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves"), card_named(s, "Sol Ring")
    for c in (bears, elves, ring):  # one at a time: the Sol Ring on top, the Elves the top creature card
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    offered = []

    def pick(d):
        ids = [o.id for o in d.options]
        if elves.id in ids or bears.id in ids:
            offered.append(set(ids))
            return [elves.id] if exile else []
        return None

    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s, pick)
    assert offered == [{elves.id}]
    assert (s.state.cards[elves.id].zone == "p1:exile") == exile
    assert (s.state.cards[ghoul.id].zone == "p1:battlefield") == exile
    check(s)


def test_cloaked_cadet_draws_once_a_turn_for_counters_on_humans(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Cloaked Cadet", "Probe Human", "Probe Counters", "Probe Counters"])
    put(s, "Cloaked Cadet"), put(s, "Probe Human")
    to_phase(s, "main1", 3)
    first, second = (c for c in s.state.cards.values() if c.name == "Probe Counters")
    act(s, "p1", type="move", card_ids=[first.id, second.id], to={"zone": "hand"})
    hand = len(s.state.zones["p1:hand"])
    cast_card(s, first, G=1)  # counters on two Humans at once: one card (the ruling)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1
    cast_card(s, second, G=1)  # only once each turn
    assert len(s.state.zones["p1:hand"]) == hand - 2 + 1
    check(s)


def test_tenuous_truce_draws_at_the_enchanted_opponents_end_step(cards):
    from tests.test_rules_wave30m_durations import three, to_phase

    s = three(cards, ["Tenuous Truce"], [], [])
    cast_it(s, "Tenuous Truce", pick=lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None, W=1, C=1)
    truce = card_named(s, "Tenuous Truce")
    assert s.state.cards[truce.id].attached_player == "p2"
    stops(s, "end")
    to_phase(s, "end", 1)
    run(s)  # not at Alice's own end step
    to_phase(s, "end", 2)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    run(s)
    assert {p: len(s.state.zones[f"{p}:hand"]) - hands[p] for p in ("p1", "p2", "p3")} == {"p1": 1, "p2": 1, "p3": 0}
    check(s)


@pytest.mark.parametrize("who,at,gone", [("p1", "p2", True), ("p1", "walker", True), ("p2", "p1", True), ("p3", "p1", False)])
def test_tenuous_truce_is_sacrificed_when_you_and_the_enchanted_opponent_attack_each_other(cards, who, at, gone):
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ["Tenuous Truce", "Grizzly Bears"], ["Grizzly Bears", "Probe Walker"], ["Grizzly Bears"])
    cast_it(s, "Tenuous Truce", pick=lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None, W=1, C=1)
    truce, attacker, walker = card_named(s, "Tenuous Truce"), put(s, "Grizzly Bears", who), put(s, "Probe Walker", "p2")
    act(s, "p2", type="set_counter", card_id=walker.id, kind="loyalty", value=5)
    declare(s, {"p1": 4, "p2": 2, "p3": 3}[who], [(attacker, walker.id if at == "walker" else at)])
    run(s)
    assert (s.state.cards[truce.id].zone == "p1:graveyard") == gone
    check(s)


def test_day_of_the_dragons_trades_creatures_for_dragons_and_back(cards):
    s = build(cards, ["Day of the Dragons", "Grizzly Bears", "Llanowar Elves", "Capsize", "Raise the Alarm"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast_it(s, "Raise the Alarm", W=1, C=1)
    cast_it(s, "Day of the Dragons", U=3, C=4)
    assert s.state.cards[bears.id].zone == "p1:exile" and s.state.cards[elves.id].zone == "p1:exile"
    dragons = [c for c in s.state.cards.values() if c.name == "Dragon" and c.zone == "p1:battlefield"]
    assert len(dragons) == 4  # the Soldier tokens count too (the ruling)
    # the enchantment leaves: the Dragons are sacrificed, the exiled cards return
    cast_card(s, card_named(s, "Capsize"), targets=[card_named(s, "Day of the Dragons").id], U=2, C=1)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[elves.id].zone == "p1:battlefield"
    assert not [c for c in s.state.cards.values() if c.name == "Dragon" and c.zone == "p1:battlefield"]
    check(s)


def _stacked(s, name):
    return sum(1 for x in s.state.log if f"{name}’s ability" in "".join(p.t or "" for p in x.parts) and "put an ability on the stack" in "".join(p.t or "" for p in x.parts))


def test_magmatic_galleon_one_treasure_for_a_batch_of_excess_damage(cards):
    s = build(cards, ["Magmatic Galleon", "Pyroclasm"], ["Llanowar Elves", "Llanowar Elves", "Grizzly Bears"])
    put(s, "Magmatic Galleon")
    for c in [c for c in s.state.cards.values() if c.owner == "p2" and c.name in ("Llanowar Elves", "Grizzly Bears")]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "battlefield"})
    cast_it(s, "Pyroclasm", R=1, C=1)  # 2 damage: excess to each 1/1 Elf, none to the 2/2 Bears (120.10)
    assert len([c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]) == 1  # one for the batch (603.2c)
    check(s)


def test_clandestine_meddler_surveils_when_a_suspected_creature_attacks(cards):
    s = build(cards, ["Clandestine Meddler", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    cast_it(s, "Clandestine Meddler", pick=lambda d: [bears.id] if bears.id in [o.id for o in d.options] else None, B=1, C=2)
    meddler = card_named(s, "Clandestine Meddler")
    declare(s, 3, [(meddler, "p2")])  # not suspected: nothing
    run(s)
    assert _stacked(s, "Clandestine Meddler") == 1  # (its enters ability only)
    declare(s, 5, [(bears, "p2")])
    run(s)
    assert _stacked(s, "Clandestine Meddler") == 2
    check(s)


# -- batch 7: the caster's {1}, a damage condition, a cast trigger's sacrifice ----------------------------------------------------------------
BATCH7 = ["Horn of Plenty", "Antagonism", "Mana Vortex", "Curse Artifact"]
PROMOTED += BATCH7


@pytest.mark.parametrize("name", BATCH7)
def test_wave100a_batch7_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_horn_of_plenty_the_caster_pays_to_draw_at_the_next_end_step(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Horn of Plenty", "Grizzly Bears"])
    put(s, "Horn of Plenty")
    stops(s, "end")
    cast_it(s, "Grizzly Bears", pick=lambda d: ["pay"] if "pay" in [o.id for o in d.options] else None, G=1, C=2)
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "end", 1)
    run(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_antagonism_spares_a_player_whose_opponent_was_dealt_damage(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Antagonism", "Lightning Bolt"])
    put(s, "Antagonism")
    stops(s, "end")
    to_phase(s, "end", 1)
    run(s)
    assert s.state.players["p1"].life == 38  # nobody was dealt damage
    to_phase(s, "main1", 3)
    bolt = card_named(s, "Lightning Bolt")
    cast_card(s, bolt, targets=["p2"], R=1)
    to_phase(s, "end", 3)
    run(s)
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 40 - 2 - 3  # Bob, Alice's opponent, was dealt damage
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_mana_vortex_is_countered_unless_you_sacrifice_a_land(cards, pay):
    s = build(cards, ["Mana Vortex"])
    forest = put(s, "Forest")
    put(s, "Island", "p2")  # (a land stays: its last ability would sacrifice it)
    cast_it(s, "Mana Vortex", pick=lambda d: (["pay" if pay else "decline"] if "pay" in [o.id for o in d.options] else
                                              [forest.id] if forest.id in [o.id for o in d.options] else None), U=2)
    assert (s.state.cards[forest.id].zone == "p1:graveyard") == pay
    assert card_named(s, "Mana Vortex").zone == ("p1:battlefield" if pay else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_curse_artifact_damages_the_controller_unless_they_sacrifice_it(cards, pay):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ["Curse Artifact"], ["Sol Ring"])
    ring = put(s, "Sol Ring", "p2")
    cast_it(s, "Curse Artifact", pick=lambda d: [ring.id] if ring.id in [o.id for o in d.options] else None, B=2, C=2)
    act(s, "p2", type="set_stops", own=["upkeep"], others=[], smart_pass=False)
    to_phase(s, "upkeep", 2)
    run(s, lambda d: ["pay" if pay else "decline"] if "pay" in [o.id for o in d.options] else None)
    assert (s.state.cards[ring.id].zone == "p2:graveyard") == pay
    assert s.state.players["p2"].life == (40 if pay else 38)
    check(s)


# -- batch 8: a destroy by an opponent's spell or ability --------------------------------------------------------------------------------------
PROMOTED += ["Karmic Justice"]
EXTRA += [real("Probe Shatter", "{1}{R}", 2, "Instant", "Destroy target artifact or enchantment.", None, "R")]


def test_karmic_justice_answers_an_opponents_destroy_even_of_itself(cards):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve("Karmic Justice")).level == "FULL"
    s = build(cards, ["Karmic Justice", "Sol Ring", "Probe Shatter"], ["Sol Ring", "Probe Shatter"])
    justice, ring = put(s, "Karmic Justice"), put(s, "Sol Ring")
    bobs = put(s, "Sol Ring", "p2")
    cast_card(s, card_named(s, "Probe Shatter"), targets=[ring.id], R=1, C=1)  # Alice's own destroy: nothing (608.2: not an opponent's)
    assert s.state.cards[ring.id].zone == "p1:graveyard" and s.state.cards[bobs.id].zone == "p2:battlefield"
    to_phase(s, "main1", 2)
    offered = []
    cast_card(s, card_named(s, "Probe Shatter", "p2"), "p2", targets=[justice.id], pick=offered_then(bobs.id, offered), R=1, C=1)
    assert s.state.cards[justice.id].zone == "p1:graveyard"  # (it looks back in time, 603.10a: the ruling)
    assert bobs.id in offered and justice.id not in offered and s.state.cards[bobs.id].zone == "p2:graveyard"  # "that opponent controls"
    check(s)


# -- batch 9: the source still there, power against a hand --------------------------------------------------------------------------------------
PROMOTED += ["Myr Servitor", "Noetic Scales"]


def test_myr_servitor_returns_every_graveyards_servitors_to_their_owners(cards):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve("Myr Servitor")).level == "FULL"
    s = build(cards, ["Myr Servitor", "Myr Servitor"], ["Myr Servitor"])
    mine, dead = (c for c in s.state.cards.values() if c.name == "Myr Servitor" and c.owner == "p1")
    bobs = card_named(s, "Myr Servitor", "p2")
    put(s, "Myr Servitor")
    act(s, "p1", type="move", card_ids=[dead.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[bobs.id], to={"zone": "graveyard"})
    stops(s, "upkeep")
    to_phase(s, "upkeep", 3)
    run(s)
    assert s.state.cards[dead.id].zone == "p1:battlefield" and s.state.cards[bobs.id].zone == "p2:battlefield"  # under their owners' control
    check(s)


def test_noetic_scales_bounces_that_players_creatures_bigger_than_their_hand(cards):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve("Noetic Scales")).level == "FULL"
    s = build(cards, ["Noetic Scales", "Grizzly Bears"], ["Grizzly Bears", "Probe Wall Creature", "Lightning Bolt"])
    put(s, "Noetic Scales")
    mine, bears, wall = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, "Probe Wall Creature", "p2")
    act(s, "p2", type="move", card_ids=[card_named(s, "Lightning Bolt", "p2").id], to={"zone": "hand"})  # one card: the 2-power Bears are bigger
    act(s, "p1", type="set_stops", own=["upkeep"], others=["upkeep"], smart_pass=False)
    to_phase(s, "upkeep", 2)
    run(s)
    assert s.state.cards[bears.id].zone == "p2:hand" and s.state.cards[wall.id].zone == "p2:battlefield"
    assert s.state.cards[mine.id].zone == "p1:battlefield"  # only that player's
    check(s)


PROMOTED += ["Mischievous Quanar"]


def test_mischievous_quanar_copies_a_spell_as_it_is_turned_face_up(cards):
    assert coverage.of_card_data(cards.resolve("Mischievous Quanar")).level == "FULL"
    s = build(cards, ["Mischievous Quanar", "Lightning Bolt"])
    quanar = to_hand(s, "Mischievous Quanar")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=quanar.id, face_down=True)
    run(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    mana(s, U=2, C=1)
    act(s, "p1", type="turn_face_up", card_id=quanar.id)  # a special action, with the Bolt on the stack (116.2b)
    run(s, lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None)
    assert not s.state.cards[quanar.id].face_down and s.state.players["p2"].life == 34  # the Bolt and its copy
    check(s)


PROMOTED += ["Death Match"]


@pytest.mark.parametrize("accept", [True, False])
def test_death_match_the_entering_creatures_controller_chooses(cards, accept):
    assert coverage.of_card_data(cards.resolve("Death Match")).level == "FULL"
    s = build(cards, ["Death Match", "Grizzly Bears"], ["Llanowar Elves"])
    put(s, "Death Match")
    bears = put(s, "Grizzly Bears")
    asked = []

    def pick(d):
        ids = [o.id for o in d.options]
        if bears.id in ids:
            asked.append(d.player)
            return [bears.id]
        if "pay" in ids:
            asked.append(d.player)
            return ["pay" if accept else "decline"]
        return None

    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main1", 2)
    cast_it(s, "Llanowar Elves", "p2", pick=pick, G=1)
    assert asked == ["p2", "p2"]  # Bob chooses the target and whether (not Alice, who controls the ability)
    assert (s.state.cards[bears.id].zone == "p1:graveyard") == accept
    check(s)


PROMOTED += ["Gate to the Aether"]


def test_gate_to_the_aether_each_player_may_put_a_revealed_permanent_card(cards):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve("Gate to the Aether")).level == "FULL"
    s = build(cards, ["Gate to the Aether", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Gate to the Aether")
    bolt, bears = card_named(s, "Lightning Bolt"), card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "library"}, position="top")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="set_stops", own=["upkeep"], others=["upkeep"], smart_pass=False)
    to_phase(s, "upkeep", 2)
    run(s, lambda d: ["yes"] if "yes" in [o.id for o in d.options] else None)
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[bears.id].controller == "p2"
    to_phase(s, "upkeep", 3)
    assert not run(s) and s.state.cards[bolt.id].zone == "p1:library"  # an instant: nothing offered
    check(s)


PROMOTED += ["Fearless Swashbuckler"]


def test_fearless_swashbuckler_loots_when_a_pirate_and_a_vehicle_attacked(cards):
    from tests.test_rules_wave30m_durations import to_phase

    assert coverage.of_card_data(cards.resolve("Fearless Swashbuckler")).level == "FULL"
    s = build(cards, ["Fearless Swashbuckler", "Sky-Skiff", "Grizzly Bears"])
    swash, skiff, pilot = put(s, "Fearless Swashbuckler"), put(s, "Sky-Skiff"), put(s, "Grizzly Bears")
    declare(s, 3, [(swash, "p2")])  # a Pirate alone: it doesn't trigger (603.4)
    run(s)
    assert _stacked(s, "Fearless Swashbuckler") == 0
    to_phase(s, "main1", 5)
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1, crew=[pilot.id])
    run(s)
    hand = len(s.state.zones["p1:hand"])
    declare(s, 5, [(swash, "p2"), (skiff, "p2")])
    run(s)
    assert _stacked(s, "Fearless Swashbuckler") == 1 and len(s.state.zones["p1:hand"]) == hand + 3 - 2
    check(s)


PROMOTED += ["Volatile Arsonist // Dire-Strain Anarchist"]


def test_volatile_arsonist_pings_up_to_one_creature_player_and_planeswalker(cards):
    assert coverage.of_card_data(cards.resolve("Volatile Arsonist // Dire-Strain Anarchist")).level == "FULL"
    s = build(cards, ["Volatile Arsonist // Dire-Strain Anarchist"], ["Grizzly Bears", "Probe Walker"])
    arsonist = put(s, "Volatile Arsonist // Dire-Strain Anarchist")
    bears, walker = put(s, "Grizzly Bears", "p2"), put(s, "Probe Walker", "p2")
    act(s, "p2", type="set_counter", card_id=walker.id, kind="loyalty", value=5)
    declare(s, 3, [(arsonist, "p2")])
    run(s, lambda d: next(([x] for x in (bears.id, "p2", walker.id) if x in [o.id for o in d.options]), None))
    assert s.state.cards[arsonist.id].face == 1  # night by now (502.2: no spells in Bob's turn): Dire-Strain Anarchist, 2 damage each
    first = s.state.players["p2"].life_history[0]
    assert s.state.cards[bears.id].zone == "p2:graveyard" and (first.before, first.after) == (40, 38) and s.state.cards[walker.id].counters.get("loyalty") == 3
    check(s)


# -- batch 15: "whenever you clash" ---------------------------------------------------------------------------------------------------------
PROMOTED += ["Sylvan Echoes", "Entangling Trap"]


@pytest.mark.parametrize("win", [True, False])
def test_clash_triggers_after_the_clash_and_read_whether_you_won(cards, win):
    from tests.test_rules_wave30m_durations import to_phase

    for name in ("Sylvan Echoes", "Entangling Trap"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    s = build(cards, ["Sylvan Echoes", "Entangling Trap", "Research the Deep", "Grizzly Bears", "Opt"], ["Llanowar Elves", "Grizzly Bears"])
    put(s, "Sylvan Echoes"), put(s, "Entangling Trap")
    elves = put(s, "Llanowar Elves", "p2")
    mine, theirs = card_named(s, "Grizzly Bears"), card_named(s, "Grizzly Bears", "p2")
    revealed = mine if win else card_named(s, "Opt")  # mana value 2, or 1 against Bob's 2 (701.30d)
    act(s, "p1", type="move", card_ids=[revealed.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[card_named(s, "Forest").id], to={"zone": "library"}, position="top")  # (drawn first)
    act(s, "p2", type="move", card_ids=[theirs.id if not win else card_named(s, "Island", "p2").id], to={"zone": "library"}, position="top")
    hand = len(s.state.zones["p1:hand"])
    cast_it(s, "Research the Deep", pick=lambda d: [elves.id] if elves.id in [o.id for o in d.options] else None, U=1, C=1)
    assert s.state.cards[elves.id].tapped  # Entangling Trap, won or not
    assert len(s.state.zones["p1:hand"]) == hand + (3 if win else 1)  # Research's draw; won: it returns, and Sylvan Echoes draws
    to_phase(s, "main1", 2)
    assert s.state.cards[elves.id].tapped == win  # it didn't untap during Bob's untap step only when Alice won
    check(s)


PROMOTED += ["Phyrexian Dreadnought"]
EXTRA += [real("Probe Giant", "{5}{G}", 6, "Creature — Giant", "", ("6", "6"), "G")]


@pytest.mark.parametrize("pay", [True, False])
def test_phyrexian_dreadnought_needs_twelve_power_of_sacrifices(cards, pay):
    from app.game.errors import ActionError

    assert coverage.of_card_data(cards.resolve("Phyrexian Dreadnought")).level == "FULL"
    s = build(cards, ["Phyrexian Dreadnought", "Probe Giant", "Probe Giant", "Grizzly Bears"])
    giants, bears = [c for c in s.state.cards.values() if c.name == "Probe Giant"], put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[g.id for g in giants], to={"zone": "battlefield"})

    def pick(d):
        if d.min_choices or bears.id not in [o.id for o in d.options]:
            return None
        if pay:
            with pytest.raises(ActionError, match="12 or greater"):  # 8 power isn't enough (118.3)
                act(s, "p1", type="choose", decision_id=d.id, option_ids=[giants[0].id, bears.id])
        return [g.id for g in giants] if pay else []

    cast_it(s, "Phyrexian Dreadnought", pick=pick, C=1)
    assert card_named(s, "Phyrexian Dreadnought").zone == ("p1:battlefield" if pay else "p1:graveyard")
    assert all(s.state.cards[g.id].zone == ("p1:graveyard" if pay else "p1:battlefield") for g in giants)
    check(s)


PROMOTED += ["Keldon Firebombers"]


def test_keldon_firebombers_each_player_keeps_three_lands(cards):
    assert coverage.of_card_data(cards.resolve("Keldon Firebombers")).level == "FULL"
    s = build(cards, ["Keldon Firebombers"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:5]
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:2]
    act(s, "p1", type="move", card_ids=[c.id for c in forests], to={"zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[c.id for c in islands], to={"zone": "battlefield"})
    cast_it(s, "Keldon Firebombers", R=2, C=3)
    assert sum(s.state.cards[c.id].zone == "p1:battlefield" for c in forests) == 3
    assert all(s.state.cards[c.id].zone == "p2:battlefield" for c in islands)  # (two: nothing to sacrifice)
    check(s)


PROMOTED += ["O-Kagachi, Vengeful Kami"]


@pytest.mark.parametrize("at", ["p1", "walker", None])
def test_o_kagachi_exiles_only_from_a_player_who_attacked_you_last_turn(cards, at):
    assert coverage.of_card_data(cards.resolve("O-Kagachi, Vengeful Kami")).level == "FULL"
    s = build(cards, ["O-Kagachi, Vengeful Kami", "Probe Walker"], ["Grizzly Bears", "Sol Ring"])
    kami, walker = put(s, "O-Kagachi, Vengeful Kami"), put(s, "Probe Walker")
    act(s, "p1", type="set_counter", card_id=walker.id, kind="loyalty", value=5)
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    if at:
        declare(s, 2, [(bears, walker.id if at == "walker" else at)])  # (only attacking Alice's planeswalker isn't attacking her: the ruling)
    run(s)
    declare(s, 3, [(kami, "p2")])
    run(s, lambda d: [ring.id] if ring.id in [o.id for o in d.options] else None)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "main2", 3)
    assert (s.state.cards[ring.id].zone == "p2:exile") == (at == "p1")
    check(s)
