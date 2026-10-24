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
