"""-- engine token stacks -- docs/TOKEN_STACKS.md. Sixteen token doublers turned one Goblin into 65,536 objects and froze the server; now one
instruction making more than ``STACK_FROM`` identical tokens makes one stack object ("Goblin ×131,072") that the rules treat as that many:

* counting reads every member ("X is the number of Goblins you control");
* all-at-once effects (an anthem, "destroy all creatures", damage to each creature) act on every member alike;
* a choice that singles out a member (a target, a sacrifice, a blocker) splits exactly one member off first;
* an unblocked attacking stack deals each member's damage (510.1a, 510.2);
* anything the engine can't treat exactly (a "whenever a creature dies" trigger, an ability that counts some other way) spreads a small
  stack into separate tokens, and refuses (never freezes) with a big one.

Real Oracle text; every scenario checks the replay and a save/load round trip (wave9c_kit.check).
"""

from __future__ import annotations

import time

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.views import build_view
from tests.game_helpers import act, deck, enable
from tests.pod_c_kit import ch, mana, settle
from tests.test_rules_pod_adrix import EXTRA as ADRIX_EXTRA
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

EXTRA = [
    *ADRIX_EXTRA,
    real('Dragon Fodder', '{1}{R}', 2, 'Sorcery', 'Create two 1/1 red Goblin creature tokens.', None, 'R'),
    real('Glorious Anthem', '{1}{W}{W}', 3, 'Enchantment', 'Creatures you control get +1/+1.', None, 'W'),
    real('Wrath of God', '{2}{W}{W}', 4, 'Sorcery', "Destroy all creatures. They can't be regenerated.", None, 'W'),
    real('Pyroclasm', '{1}{R}', 2, 'Sorcery', 'Pyroclasm deals 2 damage to each creature.', None, 'R'),
    real('Shock', '{R}', 1, 'Instant', 'Shock deals 2 damage to any target.', None, 'R'),
    real('Goblin Bombardment', '{1}{R}', 2, 'Enchantment', 'Sacrifice a creature: Goblin Bombardment deals 1 damage to any target.', None, 'R'),
    real('Soul Warden', '{W}', 1, 'Creature — Human Cleric', 'Whenever another creature enters, you gain 1 life.', ('1', '1'), 'W'),
    real('Blood Artist', '{1}{B}', 2, 'Creature — Vampire',
         'Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.', ('0', '1'), 'B'),
    real('Grizzly Bears', '{1}{G}', 2, 'Creature — Bear', '', ('2', '2'), 'G'),
    real("Ajani's Pridemate", '{1}{W}', 2, 'Creature — Cat Soldier', 'Whenever you gain life, put a +1/+1 counter on this creature.',
         ('2', '2'), 'W'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


GOBLIN = {"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "colors": ["R"]}


def table(cards, mine=(), theirs=()):
    """Alice (Krenko, Mob Boss) against Bob (Atraxa), unshuffled, in Alice's first main phase."""
    alice = deck(cards, "Krenko, Mob Boss", [*_counted(mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*_counted(theirs), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def _counted(names):
    out: dict[str, int] = {}
    for n in names:
        out[n] = out.get(n, 0) + 1
    return [(k, n) for n, k in out.items()]


def put(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield"))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def cast(s, name, *picks, pid="p1", **kw):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield"))
    if not c.zone.endswith(":hand"):
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    return settle(s, *picks)


def goblins(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Goblin" and c.zone == f"{pid}:battlefield"]


def members(s, pid="p1"):
    return sum(c.quantity for c in goblins(s, pid))


def stack_of(s, pid="p1"):
    big = [c for c in goblins(s, pid) if c.quantity > 1]
    assert len(big) == 1, [(c.id, c.quantity) for c in goblins(s, pid)]
    return big[0]


def doublers(s, n):
    """Adrix and Nev plus ``n`` Primal Vigors (each doubles every token creation: 616.1f)."""
    put(s, "Adrix and Nev, Twincasters")
    for _ in range(n):
        put(s, "Primal Vigor")


def fodder(s):
    mana(s, R=2)
    cast(s, "Dragon Fodder")


# -- the user's case ----------------------------------------------------------------------------------------------------------------
def test_sixteen_doublers_make_one_goblin_stack_fast(cards):
    """Adrix and Nev and fifteen copies of it (Spark Double: not legendary) double Dragon Fodder's two Goblins sixteen times: 131,072 Goblins
    as one object, made in well under a second (before: 131,072 objects, and the server froze)."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", *["Spark Double"] * 15])
    put(s, "Adrix and Nev, Twincasters")
    for _ in range(15):
        mana(s, U=4)
        cast(s, "Spark Double", "Adrix and Nev")
    copies = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and ch(s, c).name == "Adrix and Nev, Twincasters"]
    assert len(copies) == 16
    mana(s, R=2)
    began = time.perf_counter()
    cast(s, "Dragon Fodder")
    took = time.perf_counter() - began
    stack = stack_of(s)
    assert stack.quantity == 2 * 2 ** 16 and len(goblins(s)) == 1
    assert took < 2.0, took
    # the table shows one card with its count, the same for every viewer (a stack is public)
    for viewer in ("p1", "p2"):
        shown = build_view(s.state, viewer)["cards"][stack.id]
        assert shown["quantity"] == 131072 and shown["name"] == "Goblin"
    assert any("131,072 Goblin tokens" in str(e.model_dump()) for e in s.state.log)
    check(s)


def stacked(cards, mine=(), theirs=(), *, vigors=7):
    """Adrix and Nev with ``vigors`` Primal Vigors, then Dragon Fodder: 2 × 2^(vigors+1) Goblins (512 with seven) in one stack."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", *["Primal Vigor"] * vigors, *mine], theirs)
    doublers(s, vigors)
    fodder(s)
    return s


def until_phase(s, active, phase, limit=200):
    for _ in range(limit):
        settle(s)
        if s.state.turn.active_player == active and s.state.turn.phase == phase and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


# -- counting -----------------------------------------------------------------------------------------------------------------------
def test_krenko_counts_every_goblin_in_the_stack(cards):
    """"X is the number of Goblins you control": every member counts (a stack of 512 and Krenko himself: 513), then doubled eight times."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", *["Primal Vigor"] * 7])
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    doublers(s, 7)
    until_phase(s, "p2", "main1")
    until_phase(s, "p1", "main1")
    fodder(s)
    assert members(s) == 512
    act(s, "p1", type="activate_ability", card_id=krenko.id, ability=0)
    settle(s)
    assert members(s) == 512 + 513 * 2 ** 8
    assert sorted(c.quantity for c in goblins(s)) == [512, 513 * 256]
    check(s)


# -- all at once ----------------------------------------------------------------------------------------------------------------------
def test_an_anthem_gives_every_member_its_bonus(cards):
    s = stacked(cards, ["Glorious Anthem"])
    put(s, "Glorious Anthem")
    stack = stack_of(s)
    assert ch(s, stack).pt == (2, 2) and stack.quantity == 512
    check(s)


def test_destroy_all_creatures_takes_the_whole_stack(cards):
    s = stacked(cards, ["Wrath of God"])
    mana(s, W=4)
    cast(s, "Wrath of God")
    assert goblins(s) == []
    check(s)


def test_damage_to_each_creature_kills_every_member(cards):
    s = stacked(cards, ["Pyroclasm"])
    mana(s, R=2)
    cast(s, "Pyroclasm")
    assert goblins(s) == []
    check(s)


# -- singling out ---------------------------------------------------------------------------------------------------------------------
def test_shock_targets_one_member(cards):
    """115.1: a target is one object. The chosen card is one Goblin (it dies); the other 511 stay one stack."""
    s = stacked(cards, ["Shock"])
    stack = stack_of(s)
    mana(s, R=1)
    cast(s, "Shock", targets=[stack.id])
    assert members(s) == 511 and stack_of(s).quantity == 511
    assert not s.state.cards.get(stack.id) or not s.state.cards[stack.id].zone.endswith("battlefield")
    check(s)


def test_sacrificing_one_member_for_goblin_bombardment(cards):
    s = stacked(cards, ["Goblin Bombardment"])
    bombardment = put(s, "Goblin Bombardment")
    stack = stack_of(s)
    life = s.state.players["p2"].life
    act(s, "p1", type="activate_ability", card_id=bombardment.id, ability=0, targets=["p2"],
        cost_choices=[{"component": 0, "cards": [stack.id]}])
    settle(s)
    assert members(s) == 511 and s.state.players["p2"].life == life - 1
    check(s)


# -- combat ---------------------------------------------------------------------------------------------------------------------------
def to_attack(s):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no attack step")


def finish_combat(s):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            settle(s)
        elif s.state.turn.phase in ("main2", "end"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def test_attacking_with_part_of_a_stack(cards):
    """Split off 150 (the table's "Split off…"), attack with them: Bob takes 150; the other 362 stay home, untapped. (A part of at most
    100 is spread into separate tokens at once, as any small stack.)"""
    s = stacked(cards)
    until_phase(s, "p2", "main1")  # (the Goblins were made this turn: summoning sick)
    until_phase(s, "p1", "main1")
    stack = stack_of(s)
    act(s, "p2", type="set_life", player="p2", value=1000)
    act(s, "p1", type="split_stack", card_id=stack.id, count=150)
    part = next(c for c in goblins(s) if c.quantity == 150)
    to_attack(s)
    life = s.state.players["p2"].life
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": part.id, "target": "p2"}])
    finish_combat(s)
    assert s.state.players["p2"].life == life - 150
    home = next(c for c in goblins(s) if c.quantity == 362)
    assert not home.tapped and s.state.cards[part.id].tapped
    check(s)


def test_a_blocker_blocks_one_member(cards):
    """509.1a: a blocker blocks one attacking creature. Bob's Grizzly Bears blocks the attacking stack: one Goblin is blocked (and dies),
    the other 511 deal 511 damage."""
    s = stacked(cards, theirs=["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    until_phase(s, "p2", "main1")
    until_phase(s, "p1", "main1")
    act(s, "p2", type="set_life", player="p2", value=1000)
    stack = stack_of(s)
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": stack.id, "target": "p2"}])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": stack.id}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    finish_combat(s)
    assert s.state.players["p2"].life == 1000 - 511
    assert members(s) == 511 and stack_of(s).quantity == 511
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[bears.id].damage == 1
    check(s)


# -- what the engine can't treat exactly ------------------------------------------------------------------------------------------------
def test_a_dies_trigger_refuses_a_huge_stack_instead_of_freezing(cards):
    """Blood Artist triggers once per creature that dies (603.2c): a stack can't be treated exactly, and 131,072 tokens one object each
    would freeze the server, so the creation is refused (nothing changes) and the players are told to finish it by hand."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", "Blood Artist", *["Primal Vigor"] * 15])
    doublers(s, 15)
    put(s, "Blood Artist")
    mana(s, R=2)
    fodder_card = next(c for c in s.state.cards.values() if c.name == "Dragon Fodder")
    act(s, "p1", type="move", card_ids=[fodder_card.id], to={"zone": "hand"})
    began = time.perf_counter()
    with pytest.raises(ActionError, match="Pause automation"):
        act(s, "p1", type="cast_spell", card_id=fodder_card.id)
        settle(s)
    assert time.perf_counter() - began < 5
    assert goblins(s) == []
    check(s)


def test_a_dies_trigger_keeps_small_creations_one_object_each(cards):
    """Below the limit, with Blood Artist there, the Goblins are made one object each, as before stacks existed."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", "Blood Artist", *["Primal Vigor"] * 5])
    doublers(s, 5)
    put(s, "Blood Artist")
    fodder(s)
    assert members(s) == 128 and len(goblins(s)) == 128
    check(s)


def test_a_small_stack_is_spread_when_an_observer_arrives(cards):
    """A stack of 128 is kept while nothing could tell; Blood Artist entering spreads it (the tokens were already there: no event)."""
    s = stacked(cards, ["Blood Artist"], vigors=5)
    assert stack_of(s).quantity == 128
    put(s, "Blood Artist")
    act(s, "p1", type="pass_priority")
    assert members(s) == 128 and len(goblins(s)) == 128
    check(s)


def test_a_huge_stack_refuses_what_it_cant_do_exactly(cards):
    """Blood Artist on the battlefield beside 131,072 Goblins: the next action is refused with the reason, nothing freezes."""
    s = stacked(cards, ["Blood Artist"], vigors=15)
    assert stack_of(s).quantity == 131072
    put(s, "Blood Artist")
    with pytest.raises(ActionError, match="Blood Artist"):
        act(s, "p1", type="pass_priority")
    check(s)


def test_soul_warden_triggers_once_per_member(cards):
    """603.2c: 1,024 Goblins entered at once: Soul Warden triggers 1,024 times; Alice gains exactly 1,024 life. Nothing reads life gain,
    so the identical triggers are one folded trigger (732.2a), fast."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", "Soul Warden", *["Primal Vigor"] * 8])
    doublers(s, 8)
    put(s, "Soul Warden")
    life = s.state.players["p1"].life
    began = time.perf_counter()
    fodder(s)
    took = time.perf_counter() - began
    assert stack_of(s).quantity == 1024
    assert s.state.players["p1"].life == life + 1024
    assert took < 3.0, took
    check(s)


def test_soul_warden_with_a_life_reader_isnt_folded(cards):
    """Ajani's Pridemate-like "whenever you gain life" would trigger once per life gain: the triggers can't be folded, and 1,024 separate
    ones are too many, so the creation is refused (and a small creation is made one Goblin at a time, each triggering once)."""
    s = table(cards, ["Adrix and Nev, Twincasters", "Dragon Fodder", "Soul Warden", "Ajani's Pridemate", *["Primal Vigor"] * 8])
    doublers(s, 8)
    put(s, "Soul Warden")
    put(s, "Ajani's Pridemate")
    life = s.state.players["p1"].life
    with pytest.raises(ActionError, match="Pause automation"):
        fodder(s)
    assert goblins(s) == [] and s.state.players["p1"].life == life
    check(s)


def test_sandbox_stack_bigger_than_the_limit_stays_a_stack_when_automation_resumes(cards):
    """A stack made by hand while automation was paused isn't spread one object per token when it is bigger than the limit (that froze
    the server); with nothing on the table that could tell, the engine keeps it as a stack."""
    s = table(cards)
    act(s, "p1", type="configure", automation_paused=True)
    act(s, "p1", type="create_token", player="p1", token=GOBLIN, count=1)
    stack = goblins(s)[0]
    for _ in range(3):
        act(s, "p1", type="stack_adjust", card_id=stack.id, delta=1000)
    act(s, "p1", type="configure", automation_paused=False)
    assert members(s) == 3001 and len(goblins(s)) == 1
    act(s, "p1", type="pass_priority")
    assert members(s) == 3001 and len(goblins(s)) == 1
    with pytest.raises(ActionError, match="too big to spread"):
        act(s, "p1", type="expand_stack", card_id=stack.id)
    check(s)
