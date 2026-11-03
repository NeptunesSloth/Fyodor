"""The pod's Atraxa deck (tests/fixtures/soak_decks/atraxa_exp_bar_low.txt, "my exp bar is low"): its plan, with real Oracle text.

Atraxa proliferates every end step; the deck stacks experience counters (Ezuri, Claw of Progress, Meren, Minthara), counter doublers (Vorinclex,
Monstrous Raider; Doubling Season), extra proliferates (Tekuthal, Ezuri, Stalker of Spheres) and counter wins (Darksteel Reactor, Simic Ascendancy).
The pod deck audit checked these together:

* Atraxa's end-step proliferate gives a player experience and poison counters too (701.34a, 122.1); Meren's trigger, ordered to resolve after it,
  reads the new experience count (603.3b).
* Tekuthal: each proliferate is two (614.1a), and Ezuri draws for each; a Spark Double copy of Tekuthal (not legendary) makes it four (616.1: the
  second replacement applies to the event the first made).
* Vorinclex doubles counters put on a player (experience) and on permanents; Doubling Season only permanents you control (614.1a, 616.1).
* Ezuri's +1/+1 counters grow Simic Ascendancy by "that many" (after both doublers), and the doublers double the growth counters too.
* Deepglow Skate doubles a kind of counter by putting that many more (701.10e), which Vorinclex doubles again: Darksteel Reactor wins at once.
* Spark Double copying Atraxa isn't legendary and its extra +1/+1 counter is doubled by Doubling Season.
* Minthara's ward and power bonus follow the experience count.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, mana, pt, put, to_hand, zone_of

EXTRA = [
    real('Tekuthal, Inquiry Dominus', '{2}{U}{U}', 4, 'Legendary Creature — Phyrexian Horror',
         'Flying\nIf you would proliferate, proliferate twice instead.\n{1}{U/P}{U/P}, Remove three counters from among other artifacts, creatures, and planeswalkers you control: Put an indestructible counter on Tekuthal. ({U/P} can be paid with either {U} or 2 life.)', ("3", "5"), 'U'),
    real('Ezuri, Stalker of Spheres', '{2}{G}{U}', 4, 'Legendary Creature — Phyrexian Elf Warrior',
         'When Ezuri enters, you may pay {3}. If you do, proliferate twice.\nWhenever you proliferate, draw a card.', ("3", "3"), 'GU'),
    real('Vorinclex, Monstrous Raider', '{4}{G}{G}', 6, 'Legendary Creature — Phyrexian Praetor',
         'Trample, haste\nIf you would put one or more counters on a permanent or player, put twice that many of each of those kinds of counters on that permanent or player instead.\nIf an opponent would put one or more counters on a permanent or player, they put half that many of each of those kinds of counters on that permanent or player instead, rounded down.', ("6", "6"), 'G'),
    real('Doubling Season', '{4}{G}', 5, 'Enchantment',
         'If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.', None, 'G'),
    real('Darksteel Reactor', '{4}', 4, 'Artifact',
         'Indestructible (Effects that say "destroy" don\'t destroy this artifact.)\nAt the beginning of your upkeep, you may put a charge counter on this artifact.\nWhen this artifact has twenty or more charge counters on it, you win the game.', None, ''),
    real('Ezuri, Claw of Progress', '{2}{G}{U}', 4, 'Legendary Creature — Phyrexian Elf Warrior',
         'Whenever a creature you control with power 2 or less enters, you get an experience counter.\nAt the beginning of combat on your turn, put X +1/+1 counters on another target creature you control, where X is the number of experience counters you have.', ("3", "3"), 'GU'),
    real('Thrummingbird', '{1}{U}', 2, 'Creature — Phyrexian Bird Horror',
         'Flying\nWhenever this creature deals combat damage to a player, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)', ("1", "1"), 'U'),
    real('Contentious Plan', '{1}{U}', 2, 'Sorcery',
         'Proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)\nDraw a card.', None, 'U'),
    real('Simic Ascendancy', '{G}{U}', 2, 'Enchantment',
         '{1}{G}{U}: Put a +1/+1 counter on target creature you control.\nWhenever one or more +1/+1 counters are put on a creature you control, put that many growth counters on this enchantment.\nAt the beginning of your upkeep, if this enchantment has twenty or more growth counters on it, you win the game.', None, 'GU'),
    real('Deepglow Skate', '{4}{U}', 5, 'Creature — Fish',
         'When this creature enters, double the number of each kind of counter on any number of target permanents.', ("3", "3"), 'U'),
    real('Spark Double', '{3}{U}', 4, 'Creature — Illusion',
         "You may have this creature enter as a copy of a creature or planeswalker you control, except it enters with an additional +1/+1 counter on it if it's a creature, it enters with an additional loyalty counter on it if it's a planeswalker, and it isn't legendary.", ("0", "0"), 'U'),
    real('Minthara, Merciless Soul', '{2}{W}{B}', 4, 'Legendary Creature — Elf Cleric',
         'Minthara has ward {X}, where X is the number of experience counters you have.\nAt the beginning of your end step, if a permanent you controlled left the battlefield this turn, you get an experience counter.\nCreatures you control get +1/+0 for each experience counter you have.', ("2", "2"), 'BW'),
    real('Meren of Clan Nel Toth', '{2}{B}{G}', 4, 'Legendary Creature — Human Shaman',
         "Whenever another creature you control dies, you get an experience counter.\nAt the beginning of your end step, choose target creature card in your graveyard. If that card's mana value is less than or equal to the number of experience counters you have, return it to the battlefield. Otherwise, put it into your hand.", ("3", "4"), 'BG'),
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


def table(cards, theirs=()):
    """Alice plays Atraxa (her commander, put onto the battlefield), Bob Krenko; Alice is in her first main phase."""
    alice = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in NAMES), (1, "Sol Ring"), (20, "Island")])
    bob = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in theirs), (20, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "Atraxa, Praetors' Voice")
    return s


def experience(s, pid="p1"):
    return s.state.players[pid].resources.get("experience", 0)


def give(s, pid, key, n):
    act(s, pid, type="resource", player=pid, key=key, delta=n)


def counters(s, name, kind):
    return s.state.cards[card_named(s, name).id].counters.get(kind, 0)


def add(s, name, kind, n):
    act(s, "p1", type="counter", card_ids=[card_named(s, name).id], kind=kind, delta=n)


def proliferate_everything(d):
    return [o.id for o in d.options] if d.prompt.startswith("Proliferate") else []


def resolve(s, *picks, limit=60):
    """Resolve everything: a proliferate chooses everything offered, an order or choice the options labelled ``picks`` (in turn), else the first."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            want = proliferate_everything(d)
            if not want and picks:
                want = [o.id for o in d.options if (o.label or "").startswith(picks[0])][: max(d.max_choices or 1, 1)]
                picks = picks[1:] if want else picks
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack") and s.state.rules.winner is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, *picks, **kw):
    c = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    resolve(s, *picks)


def test_atraxas_end_step_proliferate_counts_for_merens_trigger_ordered_after_it(cards):
    """Three experience, Ezuri (mana value 4) in the graveyard: Atraxa's proliferate resolves first (Meren's trigger is put on the stack first),
    so Meren sees four and returns Ezuri to the battlefield. Bob's poison counters and the Reactor's charge counters grow too."""
    s = table(cards)
    put(s, "Meren of Clan Nel Toth")
    put(s, "Darksteel Reactor")
    add(s, "Darksteel Reactor", "charge", 1)
    act(s, "p1", type="move", card_ids=[card_named(s, "Ezuri, Stalker of Spheres").id], to={"zone": "graveyard"})
    give(s, "p1", "experience", 3)
    give(s, "p2", "poison", 3)
    until(s, lambda s: s.state.turn.phase == "end" and s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.kind == "order" and {o.label for o in d.options} == {"Atraxa, Praetors' Voice", "Meren of Clan Nel Toth"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith("Meren")),
                                                                next(o.id for o in d.options if o.label.startswith("Atraxa"))])
    resolve(s, "Ezuri", "No")  # (Meren's target; Ezuri's "you may pay {3}" is declined)
    assert experience(s) == 4 and s.state.players["p2"].resources["poison"] == 4 and counters(s, "Darksteel Reactor", "charge") == 2
    assert zone_of(s, "Ezuri, Stalker of Spheres") == "p1:battlefield"
    check(s)


def test_tekuthal_doubles_each_proliferate_and_ezuri_draws_for_each(cards):
    s = table(cards)
    put(s, "Tekuthal, Inquiry Dominus")
    put(s, "Ezuri, Stalker of Spheres")
    put(s, "Darksteel Reactor")
    add(s, "Darksteel Reactor", "charge", 1)
    to_hand(s, "Contentious Plan")
    library = len(s.state.zones["p1:library"])
    mana(s, U=1, C=1)
    cast(s, "Contentious Plan")
    assert counters(s, "Darksteel Reactor", "charge") == 3
    assert library - len(s.state.zones["p1:library"]) == 1 + 2  # (Contentious Plan's card, and Ezuri's for each proliferate)
    check(s)


def test_a_spark_double_copy_of_tekuthal_makes_one_proliferate_four(cards):
    s = table(cards)
    put(s, "Tekuthal, Inquiry Dominus")
    mana(s, U=1, C=3)
    cast(s, "Spark Double", "Tekuthal")
    assert s.state.cards[card_named(s, "Spark Double").id].counters.get("+1/+1") == 1
    put(s, "Darksteel Reactor")
    add(s, "Darksteel Reactor", "charge", 1)
    mana(s, U=1, C=1)
    cast(s, "Contentious Plan")
    assert counters(s, "Darksteel Reactor", "charge") == 5
    check(s)


def test_vorinclex_doubles_experience_counters_and_proliferate_and_doubling_season_does_not_touch_players(cards):
    s = table(cards)
    put(s, "Ezuri, Claw of Progress")
    put(s, "Doubling Season")
    mana(s, U=1, C=1)
    cast(s, "Thrummingbird")
    assert experience(s) == 1  # (Doubling Season: counters on permanents only)
    put(s, "Vorinclex, Monstrous Raider")
    mana(s, U=1, C=1)
    cast(s, "Contentious Plan")
    assert experience(s) == 1 + 2
    check(s)


def test_ezuris_counters_grow_simic_ascendancy_through_vorinclex_and_doubling_season(cards):
    """Four experience: Ezuri puts 4 × 2 × 2 = 16 +1/+1 counters on Thrummingbird; the Ascendancy gets "that many" growth counters, doubled twice."""
    s = table(cards)
    for name in ("Ezuri, Claw of Progress", "Vorinclex, Monstrous Raider", "Doubling Season", "Simic Ascendancy", "Thrummingbird"):
        put(s, name)
    give(s, "p1", "experience", 4)
    until(s, lambda s: s.state.turn.phase == "begin_combat" and (s.state.rules.decision is not None or s.state.zones.get("stack")))
    resolve(s, "Thrummingbird")  # (Ezuri's target)
    assert counters(s, "Thrummingbird", "+1/+1") == 16 and counters(s, "Simic Ascendancy", "growth") == 64
    check(s)


def test_deepglow_skate_and_vorinclex_win_with_darksteel_reactor_at_once(cards):
    """Seven charge counters: doubling them puts seven more (701.10e), which Vorinclex makes fourteen: 21, and the Reactor's state trigger wins."""
    s = table(cards)
    put(s, "Darksteel Reactor")
    add(s, "Darksteel Reactor", "charge", 7)
    put(s, "Vorinclex, Monstrous Raider")
    mana(s, U=1, C=4)
    cast(s, "Deepglow Skate", "Darksteel Reactor")
    assert counters(s, "Darksteel Reactor", "charge") == 21 and s.state.rules.winner == "p1"
    check(s)


def test_spark_double_copying_atraxa_isnt_legendary_and_its_counter_is_doubled(cards):
    s = table(cards)
    put(s, "Doubling Season")
    mana(s, U=1, C=3)
    cast(s, "Spark Double", "Atraxa")
    double = s.state.cards[card_named(s, "Spark Double").id]
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(double)
    assert double.zone == "p1:battlefield" and ch.name == "Atraxa, Praetors' Voice" and "Legendary" not in ch.supertypes
    assert double.counters.get("+1/+1") == 2 and zone_of(s, "Atraxa, Praetors' Voice") == "p1:battlefield"
    check(s)


def test_minthara_ward_and_power_follow_the_experience_count(cards):
    s = table(cards, theirs=["Lightning Bolt"])
    minthara = put(s, "Minthara, Merciless Soul")
    give(s, "p1", "experience", 3)
    assert pt(s, "Minthara, Merciless Soul") == (5, 2)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[minthara.id])
    resolve(s)
    assert zone_of(s, "Minthara, Merciless Soul") == "p1:battlefield" and zone_of(s, "Lightning Bolt", "p2") == "p2:graveyard"  # (ward {3} unpaid)
    check(s)
