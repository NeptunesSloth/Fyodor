"""Wave 110E: single-card builds on real Oracle text; every scenario checks the replay and a save and a load.

* Garruk, Savage Herald: -7 grants the 510.1c permission to creatures for the turn (a quoted static the granting layer now reads).
* Storm, Windrider: 508.1c/509.1b flyers can't attack its controller or block its controller's creatures; 603.2 its cast trigger grants flying to the
  creatures the spell targets (115.9b), only when the spell has such a target.
* Blaze of Glory: 509.1c the target, which can block any number of creatures, must block each attacking creature it is able to.
* Vivien's Stampede: 603.7 "at the beginning of the next main phase this turn" (the postcombat main phase, never a later turn's), counted when it resolves.
* Spin into Myth: 701.29a fateseal 2 (look at the top two cards of an opponent's library, any to the bottom, the rest back on top in any order).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_designations import put as put3
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Vivien's Stampede", "{4}{G}{G}", 6, "Sorcery",
         "Each creature you control gains vigilance, trample, and melee until end of turn. (Whenever a creature with melee attacks, it gets +1/+1 until end of turn for each opponent you attacked this combat.)\n"
         "At the beginning of the next main phase this turn, draw a card for each player who was dealt combat damage this turn.", None, "G"),
    real("Blaze of Glory", "{W}", 1, "Instant", "Cast this spell only during combat before blockers are declared.\n"
         "Target creature defending player controls can block any number of creatures this turn. It blocks each attacking creature this turn if able.", None, "W"),
    real("Storm, Windrider", "{1}{G}{W}{W}", 4, "Legendary Creature — Mutant Hero",
         "Flying\nCreatures with flying can't attack you or block creatures you control.\n"
         "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn.", ("4", "4"), "GW"),
    real("Giant Growth", "{G}", 1, "Instant", "Target creature gets +3/+3 until end of turn.", None, "G"),
    real("Garruk, Savage Herald", "{4}{G}{G}", 6, "Legendary Planeswalker — Garruk",
         "+1: Reveal the top card of your library. If it's a creature card, put it into your hand. Otherwise, put it on the bottom of your library.\n"
         "−2: Target creature you control deals damage equal to its power to another target creature.\n"
         "−7: Until end of turn, creatures you control gain \"You may have this creature assign its combat damage as though it weren't blocked.\"", None, "G"),
    real("Spin into Myth", "{3}{U}", 4, "Instant",
         "Put target creature on top of its owner's library, then fateseal 2. (To fateseal 2, look at the top two cards of an opponent's library, then put any number of them on the bottom of that player's library and the rest on top in any order.)", None, "U"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA.append(real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn.", ("5", "5"), "R"))


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


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def test_spin_into_myth_fateseals_two(cards):
    s = build(cards, ["Spin into Myth", "Shivan Dragon"])
    elf = put(s, "Shivan Dragon")
    lib = list(s.state.zones["p2:library"])
    mana(s, U=1, C=3)
    cast(s, "Spin into Myth", [elf.id])
    seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        assert d.player == "p1"  # only the fatesealing player is asked (and sees the cards)
        ids = [o.id for o in d.options]
        seen.append(d.kind)
        pick = [lib[0]] if lib[0] in ids and "bottom" not in seen else ids[: max(1, d.min_choices)]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.cards[elf.id].zone == "p1:library" and s.state.zones["p1:library"][0] == elf.id  # 701.29a, top of its owner's library
    assert sorted(s.state.zones["p2:library"]) == sorted(lib)  # same cards, only reordered
    assert s.state.zones["p2:library"][-1] == lib[0]  # first card went to the bottom
    check(s)


@pytest.mark.parametrize("grant", [True, False])
def test_garruk_minus_seven_lets_blocked_creatures_assign_as_unblocked(cards, grant):
    from tests.test_rules_group_unblocked import finish_combat, start_combat
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ["Garruk, Savage Herald", "Grizzly Bears"])
    to_phase(s, "main1", turn=1)
    bears = put3(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", turn=4)  # (no longer summoning sick)
    garruk = put3(s, "Garruk, Savage Herald", "battlefield")
    act(s, "p1", type="set_counter", card_id=garruk.id, kind="loyalty", value=7)
    if grant:
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
        while s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    before = set(s.state.cards)
    act(s, "p2", type="create_token", player="p2", token={"name": "Wall", "type_line": "Token Creature — Wall", "power": "0", "toughness": "10"})
    wall = next(c for cid, c in s.state.cards.items() if cid not in before)
    start_combat(s, [bears], [wall])
    assert finish_combat(s) == ([bears.id] if grant else [])  # 510.1c: asked only while the grant lasts
    assert s.state.players["p2"].life == (38 if grant else 40)
    check(s)


def keywords(s, card):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).keywords


@pytest.mark.parametrize("targeted", [True, False])
def test_storm_windrider_grants_flying_to_the_spells_targets(cards, targeted):
    s = build(cards, ["Storm, Windrider", "Giant Growth", "Grizzly Bears"])
    put(s, "Storm, Windrider")
    bears = put(s, "Grizzly Bears")
    mana(s, G=1)
    if targeted:
        cast(s, "Giant Growth", [bears.id])
        answer(s)
    assert ("flying" in {k.lower() for k in keywords(s, bears)}) is targeted  # 115.9b: only the spell's targets
    check(s)


def test_storm_windrider_flyers_cant_attack_its_controller(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = build(cards, ["Storm, Windrider"], ["Shivan Dragon"])
    put(s, "Storm, Windrider")
    dragon = put(s, "Shivan Dragon", "p2")
    until(s, lambda s: s.state.turn.number >= 2 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert s.state.turn.active_player == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": dragon.id, "target": "p1"}])  # 508.1c


@pytest.mark.parametrize("blocks,legal", [(0, False), (1, False), (2, True)])
def test_blaze_of_glory_forces_the_target_to_block_every_attacker(cards, blocks, legal):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = build(cards, ["Blaze of Glory", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    for c in bears:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    wall = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_prefs", full_control=True)
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in bears])
    mana(s, W=1)
    cast(s, "Blaze of Glory", [wall.id])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    pairs = [{"blocker_id": wall.id, "attacker_id": c.id} for c in bears[:blocks]]
    if legal:
        act(s, "p2", type="declare_blockers", blocks=pairs)
        check(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=pairs)


@pytest.mark.parametrize("attack", [True, False])
def test_vivien_stampede_draws_in_the_next_main_phase_for_each_damaged_player(cards, attack):
    from tests.test_rules_conditionals import until

    s = build(cards, ["Vivien's Stampede", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.active_player == "p1" and s.state.turn.phase == "main1")
    mana(s, G=2, C=4)
    cast(s, "Vivien's Stampede")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    if attack:
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if attack else 0)  # one player dealt combat damage / none
    check(s)


CHOKING = real("Choking Vines", "{X}{G}", 1, "Instant",
               "Cast this spell only during the declare blockers step.\n"
               "X target attacking creatures become blocked. Choking Vines deals 1 damage to each of those creatures. "
               "(This spell works on creatures that can't be blocked.)", None, "G")
LETHAL = real("Lethal Exploit", "{1}{B}", 2, "Instant",
              "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each modified creature you controlled as you cast this spell. "
              "(Equipment, Auras you control, and counters are modifications.)", None, "B")
EXTRA.extend([CHOKING, LETHAL])
NAMES.extend(["Choking Vines", "Lethal Exploit"])


def test_choking_vines_blocks_unblocked_attackers_and_pings_each(cards):
    """509.1h/509.3c: targets become blocked (no damage to the player); 120.3: 1 damage to each of them."""
    from tests.wave53c_kit import combat_step, creature, in_play, pool, priority_to, sandbox, settle, swing, to_postcombat

    s = sandbox(cards, "Choking Vines")
    a = creature(s, "p1", "Aaa", "5/5", text="Whenever this creature becomes blocked, you gain 1 life.")
    b = creature(s, "p1", "Bbb", "3/3")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a, b], [(guard, b)], before=None)

    vines = in_play(s, "Choking Vines")
    act(s, "p1", type="move", card_ids=[vines.id], to={"zone": "hand"})
    pool(s, "p1", G=1, C=2)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=vines.id, targets=[a.id, b.id], target_counts=[2], x_value=2)
    settle(s)  # X=2: b is already blocked, still takes 1
    assert s.state.players["p1"].life == 41 and s.state.cards[a.id].damage == 1 and s.state.cards[b.id].damage == 1
    to_postcombat(s)
    assert s.state.players["p2"].life == 40  # a is blocked, no blocker, no trample: no damage (510.1c)
    check(s)


@pytest.mark.parametrize("modified", [0, 2])
def test_lethal_exploit_counts_modified_creatures_as_cast(cards, modified):
    """601.2i/700.9: -1/-1 more per creature with a counter or attachment when the spell was cast, none for later changes."""
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import pool, priority_to, settle

    s = sandbox(cards, "Lethal Exploit")
    victim = creature(s, "p2", "Victim", "6/6")
    for i in range(modified):
        c = creature(s, "p1", f"Mod{i}", "1/1")
        act(s, "p1", type="set_counter", card_id=c.id, kind="+1/+1", value=1)
    creature(s, "p1", "Plain", "1/1")
    from tests.wave53c_kit import main_step
    main_step(s)
    spell = next(c for c in s.state.cards.values() if c.name == "Lethal Exploit")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    pool(s, "p1", B=1, C=1)
    priority_to(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    settle(s)
    from app.rules.plan import Plan
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[victim.id]).pt == (4 - modified, 4 - modified)
    check(s)
