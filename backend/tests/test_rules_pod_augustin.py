"""The pod's Grand Arbiter Augustin IV deck (tests/fixtures/soak_decks/grand_arbiter_augustin_iv_interesting.txt): its plan, with real Oracle text.

Augustin makes Alice's white and blue spells cost {1} less each (a white-and-blue spell {2} less) and her opponents' spells {1} more; the
list stacks it with Pearl Medallion, Sphere of Resistance, Thalia and God-Pharaoh's Statue. 601.2f: the total cost is the mana cost or an
alternative cost (Fierce Guardianship's "without paying its mana cost") plus increases minus reductions; 118.7a: a generic reduction takes
only generic mana, so {U}{U} stays {U}{U}. The rest of the plan: "unless that player pays" draw and Treasure engines on the taxed spells,
attack taxes that add up (508.1h), and Azor's Elocutors' filibuster win. The free-cast hint used to offer Fierce Guardianship with nothing
to counter (cast_spell refused it: no legal target, 601.2c).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import PHASES
from app.rules import coverage
from app.rules.casting import spell_cost
from app.rules.plan import Plan
from app.rules.view import hints
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

EXTRA = [
    real('Grand Arbiter Augustin IV', '{2}{W}{U}', 4, 'Legendary Creature — Human Advisor',
         'White spells you cast cost {1} less to cast.\nBlue spells you cast cost {1} less to cast.\nSpells your opponents cast cost {1} more '
         'to cast.', ('2', '3'), 'UW'),
    real('Pearl Medallion', '{2}', 2, 'Artifact', 'White spells you cast cost {1} less to cast.', None, ''),
    real('Sphere of Resistance', '{2}', 2, 'Artifact', 'Spells cost {1} more to cast.', None, ''),
    real('Thalia, Guardian of Thraben', '{1}{W}', 2, 'Legendary Creature — Human Soldier',
         'First strike\nNoncreature spells cost {1} more to cast.', ('2', '1'), 'W'),
    real("God-Pharaoh's Statue", '{6}', 6, 'Legendary Artifact',
         'Spells your opponents cast cost {2} more to cast.\nAt the beginning of your end step, each opponent loses 1 life.', None, ''),
    real('Fierce Guardianship', '{2}{U}', 3, 'Instant',
         'If you control a commander, you may cast this spell without paying its mana cost.\nCounter target noncreature spell.', None, 'U'),
    real("Azor's Elocutors", '{3}{W/U}{W/U}', 5, 'Creature — Human Advisor',
         'At the beginning of your upkeep, put a filibuster counter on this creature. Then if this creature has five or more filibuster '
         'counters on it, you win the game.\nWhenever a source deals damage to you, remove a filibuster counter from this creature.',
         ('3', '5'), 'UW'),
    real('Mana Leak', '{1}{U}', 2, 'Instant', 'Counter target spell unless its controller pays {3}.', None, 'U'),
    real('Rhystic Study', '{2}{U}', 3, 'Enchantment',
         'Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.', None, 'U'),
    real('Smothering Tithe', '{3}{W}', 4, 'Enchantment',
         'Whenever an opponent draws a card, that player may pay {2}. If the player doesn\'t, you create a Treasure token. (It\'s an artifact '
         'with "{T}, Sacrifice this token: Add one mana of any color.")', None, 'W'),
    real('Propaganda', '{2}{U}', 3, 'Enchantment',
         "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", None, 'U'),
    real('Ghostly Prison', '{2}{W}', 3, 'Enchantment',
         "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", None, 'W'),
    real('Baird, Steward of Argive', '{2}{W}{W}', 4, 'Legendary Creature — Human Soldier',
         "Vigilance\nCreatures can't attack you or planeswalkers you control unless their controller pays {1} for each of those creatures.",
         ('2', '4'), 'W'),
    real("Norn's Annex", '{3}{W/P}{W/P}', 5, 'Artifact',
         "({W/P} can be paid with either {W} or 2 life.)\nCreatures can't attack you or planeswalkers you control unless their controller "
         "pays {W/P} for each of those creatures.", None, 'W'),
    real('Irma, Part-Time Mutant', '{2}{U}', 3, 'Legendary Creature — Human Mutant Shapeshifter',
         'At the beginning of combat on your turn, Irma becomes a copy of up to one other target creature you control, except her name is '
         'Irma, Part-Time Mutant and she has this ability. Then put a +1/+1 counter on her.', ('1', '1'), 'U'),
    real('Ancient Tomb', '', 0, 'Land', '{T}: Add {C}{C}. This land deals 2 damage to you.', None, ''),
    real('Divination', '{2}{U}', 3, 'Sorcery', 'Draw two cards.', None, 'U'),
]
NAMES = [c["name"] for c in EXTRA]
MINE = [n for n in NAMES if n not in ("Grand Arbiter Augustin IV", "Divination")] + ["Counterspell", "Wrath of God", "Sol Ring"]
THEIRS = ["Divination", "Lightning Bolt", "Grizzly Bears", "Sol Ring"]


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


# -- the table --------------------------------------------------------------------------------------------------------------------------------
def build(cards, *, augustin=True):
    """Alice (Augustin's deck, Augustin on the battlefield from the command zone) and Bob; Alice is in her first main phase."""
    alice = deck(cards, "Grand Arbiter Augustin IV", [*((1, n) for n in MINE), (12, "Island")])
    bob = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in THEIRS), (12, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    if augustin:
        put(s, "Grand Arbiter Augustin IV")
    return s


def card(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = card(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_hand(s, name, pid="p1"):
    c = card(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def cost_of(s, name, pid="p1", **kw):
    c = s.state.cards[to_hand(s, name, pid).id]
    return spell_cost(s.state, c, Plan(s.state, pid, s.cards, None).ch(c), info=s.cards, player=pid, **kw).text()


def settle(s, *labels, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            want = [o.id for o in d.options if (o.label or "") in labels][: max(d.max_choices or 1, 1)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_step(s, phase, turn, *labels, limit=400):
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.rules.winner or (s.state.turn.number, PHASES.index(s.state.turn.phase)) >= (turn, PHASES.index(phase)) \
                and not s.state.zones.get("stack") and d is None:
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            want = [o.id for o in d.options if (o.label or "") in labels][: max(d.max_choices or 1, 1)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want or [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


def bob_casts_divination(s):
    """On to Bob's main phase; everyone stops for each spell; Bob casts Divination with exactly the mana it costs."""
    to_step(s, "main1", 2)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    due = cost_of(s, "Divination", "p2")
    generic = int(due.split("}")[0][1:]) if due[1].isdigit() else 0
    mana(s, "p2", U=1, **({"C": generic} if generic else {}))
    divination = card(s, "Divination", "p2")
    act(s, "p2", type="cast_spell", card_id=divination.id, targets=[])
    assert s.state.players["p2"].mana == {} and not s.state.players["p2"].mana_units
    return divination, due


# -- the scenarios ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("table", "spell", "pid", "due"), [
    ((), "Wrath of God", "p1", "{1}{W}{W}"),
    ((), "Azor's Elocutors", "p1", "{1}{W/U}{W/U}"),  # white and blue: {2} less
    ((), "Counterspell", "p1", "{U}{U}"),  # 118.7a: no generic mana to take
    ((), "Sol Ring", "p1", "{1}"),  # colorless
    (("Pearl Medallion",), "Wrath of God", "p1", "{W}{W}"),
    (("Pearl Medallion",), "Azor's Elocutors", "p1", "{W/U}{W/U}"),
    (("Sphere of Resistance",), "Mana Leak", "p1", "{1}{U}"),
    (("Sphere of Resistance",), "Counterspell", "p1", "{U}{U}"),  # 601.2f: the increase, then the reduction
    (("Sphere of Resistance", "Thalia, Guardian of Thraben"), "Counterspell", "p1", "{1}{U}{U}"),
    ((), "Lightning Bolt", "p2", "{1}{R}"),
    (("Sphere of Resistance", "Thalia, Guardian of Thraben", "God-Pharaoh's Statue"), "Lightning Bolt", "p2", "{5}{R}"),
    (("Thalia, Guardian of Thraben",), "Grizzly Bears", "p2", "{2}{G}"),  # Thalia: noncreature spells only
])
def test_cost_changes_stack(cards, table, spell, pid, due):
    s = build(cards)
    for name in table:
        put(s, name)
    assert cost_of(s, spell, pid) == due


def test_an_opponents_taxed_spell_feeds_rhystic_study_and_smothering_tithe(cards):
    """Bob pays {3}{U} for Divination (Augustin and Sphere would make it {4}{U}; here Augustin alone) and has nothing left for Rhystic
    Study's {1} (Alice draws) or Smothering Tithe's {2} for each of his two draws (two Treasures)."""
    s = build(cards)
    put(s, "Rhystic Study")
    put(s, "Smothering Tithe")
    alice = len(s.state.zones["p1:hand"])
    _, due = bob_casts_divination(s)
    assert due == "{3}{U}"
    settle(s, "Yes")
    assert len(s.state.zones["p1:hand"]) == alice + 1
    assert [c.controller for c in s.state.cards.values() if c.name == "Treasure"] == ["p1", "p1", "p1"]  # (and one for his draw step)
    check(s)


def test_fierce_guardianship_is_free_under_sphere_and_offered_only_with_a_spell_to_counter(cards):
    """Augustin is a commander on the battlefield: the alternative cost {0}, plus Sphere's {1}, minus Augustin's {1} (601.2f): nothing to pay.
    The hint doesn't offer it while there is no noncreature spell to counter (cast_spell would refuse it, 601.2c)."""
    s = build(cards)
    put(s, "Sphere of Resistance")
    guardianship = to_hand(s, "Fierce Guardianship")
    assert guardianship.id not in hints(s.state, "p1", s.cards)["free_castable"]
    divination, due = bob_casts_divination(s)
    assert due == "{4}{U}"
    while s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    assert guardianship.id in hints(s.state, "p1", s.cards)["free_castable"]
    act(s, "p1", type="cast_spell", card_id=guardianship.id, targets=[divination.id], free=True)
    assert s.state.players["p1"].mana == {}
    settle(s)
    assert s.state.cards[divination.id].zone == "p2:graveyard" and s.state.cards[guardianship.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("enough", [True, False])
def test_attack_taxes_add_up(cards, enough):
    """508.1h: Propaganda {2} + Ghostly Prison {2} + Baird {1} + Norn's Annex {W/P} for the one attacker: {5}{W/P}, the {W/P} paid with 2
    life. With {4} Bob can't attack."""
    s = build(cards, augustin=False)
    for name in ("Propaganda", "Ghostly Prison", "Baird, Steward of Argive", "Norn's Annex"):
        put(s, name)
    bears = put(s, "Grizzly Bears", "p2")
    for _ in range(100):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    mana(s, "p2", C=5 if enough else 4)
    attack = {"card_id": bears.id, "target": "p1"}
    if not enough:
        with pytest.raises(Exception, match=r"\{5\}\{W/P\}"):
            act(s, "p2", type="declare_attackers", attackers=[attack])
        return
    act(s, "p2", type="declare_attackers", attackers=[attack])
    assert s.state.cards[bears.id].attacking is not None and s.state.players["p2"].life == 38
    check(s)


def test_azors_elocutors_loses_a_counter_to_damage_and_wins_at_five(cards):
    s = build(cards)
    elocutors = put(s, "Azor's Elocutors")
    act(s, "p1", type="set_counter", card_id=elocutors.id, kind="filibuster", value=4)
    put(s, "Ancient Tomb")
    to_hand(s, "Sol Ring")
    act(s, "p1", type="cast_spell", card_id=card(s, "Sol Ring").id, targets=[])  # paid with Ancient Tomb: 2 damage to Alice
    settle(s)
    assert s.state.cards[elocutors.id].counters["filibuster"] == 3
    to_step(s, "draw", 3)
    assert s.state.cards[elocutors.id].counters["filibuster"] == 4 and s.state.rules.winner is None
    to_step(s, "draw", 5)
    assert s.state.rules.winner == "p1"
    check(s)


def test_irma_copying_augustin_doubles_both_changes(cards):
    """Irma becomes a copy of Augustin named Irma (no legend rule): white spells {2} less, Bob's spells {2} more."""
    s = build(cards)
    irma = put(s, "Irma, Part-Time Mutant")
    to_step(s, "begin_combat", 1, "Grand Arbiter Augustin IV")
    settle(s, "Grand Arbiter Augustin IV")
    assert s.state.cards[irma.id].zone == "p1:battlefield" and card(s, "Grand Arbiter Augustin IV").zone == "p1:battlefield"
    assert cost_of(s, "Wrath of God") == "{W}{W}"
    assert cost_of(s, "Sol Ring", "p2") == "{3}"
    check(s)


def test_the_table_shows_what_a_spell_costs_now(cards):
    """The castable cards in hand whose cost to cast differs from their mana cost carry that cost (hints.cost_now): Wrath of God is {1}{W}{W}
    under Augustin; Counterspell ({U}{U}: no generic to take, 118.7a) and Sol Ring (colorless) are as printed and carry nothing."""
    s = build(cards)
    wrath, counterspell, ring = (to_hand(s, n) for n in ("Wrath of God", "Counterspell", "Sol Ring"))
    mana(s, W=2, U=2, C=1)
    view_hints = hints(s.state, "p1", s.cards)
    assert {wrath.id, ring.id} <= set(view_hints["castable"])
    assert view_hints["cost_now"] == {wrath.id: "{1}{W}{W}"}
    assert counterspell.id not in view_hints["cost_now"] and ring.id not in view_hints["cost_now"]
    check(s)
