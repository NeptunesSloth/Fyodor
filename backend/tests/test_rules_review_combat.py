"""-- review (wave 14R) -- combat, blocking, phasing: regressions found reviewing waves 7R–14A, and probes of cards they made FULL.

* 509.1c: the most requirements that could be obeyed counts any legal declaration — a Lure with menace makes two able
  creatures block together; a blocker at its limit (509.1a) blocking an attacker that no requirement names must block a lure.
* 702.26b / 506.4: a permanent that phases out leaves combat, every block of a blocker of several included (509.1a).
* 702.19d: a trampler whose blockers all left assigns everything where it attacks, with no question asked.
* 702.26d/f: a phased-out permanent is the same object; a control effect that ends while it is phased out leaves it with its
  owner once it phases in; a phased-out token survives a change of controller; 800.4a: a leaving player's stolen, phased-out
  permanent goes back to its owner (phased out, 702.26n).
* Divine Smite, Teferi's Veil and Goblin Cadets on real Oracle text.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_combat import attack, automate, block, creature, decision, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches, token
from tests.test_rules_wave6c_tokens_pumps import reloaded
from tests.wave9c_kit import build, cast, put, to_hand
from tests.wave9c_kit import mana as add_mana

WALL = "This creature can block an additional creature each combat."
HAYSTACK = "{2}, {T}: Target creature you control phases out. (Treat it and anything attached to it as though they don't exist until your next turn.)"  # noqa: E501
LURE = "All creatures able to block this creature do so."
THIEF = "{2}: Gain control of target creature until end of turn."

EXTRA = [
    card("Divine Smite", number="R01", mana_cost="{W}", cmc=1.0, type_line="Instant", colors=["W"], color_identity=["W"],
         oracle_text="Target creature or planeswalker an opponent controls phases out. If that permanent is black, exile it instead. (If it phases out, treat it and anything attached to it as though they don't exist until its controller's next turn.)"),  # noqa: E501
    card("Teferi's Veil", number="R02", mana_cost="{1}{U}", cmc=2.0, type_line="Enchantment", colors=["U"], color_identity=["U"],
         oracle_text="Whenever a creature you control attacks, it phases out at end of combat. (While it's phased out, it's treated as though it doesn't exist. It phases in before you untap during your next untap step.)"),  # noqa: E501
    card("Goblin Cadets", number="R03", mana_cost="{R}", cmc=1.0, type_line="Creature — Goblin", colors=["R"], color_identity=["R"],
         power="2", toughness="2",
         oracle_text="Whenever this creature blocks or becomes blocked, target opponent gains control of it. (This removes this creature from combat.)"),  # noqa: E501
    card("Vampire Nighthawk", number="R04", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Creature — Vampire Shaman", colors=["B"],
         color_identity=["B"], power="2", toughness="3", oracle_text="Flying\nDeathtouch\nLifelink"),
    card("Grizzly Bears", number="R05", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", colors=["G"], color_identity=["G"],
         power="2", toughness="2", oracle_text=""),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def mana(s, pid, n):
    act(s, pid, type="add_mana", player=pid, mana={"C": n})


def stops(s):
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")


def artifact(s, pid, name, text):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Artifact", "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def passes(s, *pids):
    for pid in pids:
        act(s, pid, type="pass_priority")


def run_to(s, number, phase="main1"):
    """Pass (declaring nothing, taking the first choices) until turn ``number``'s ``phase``."""
    for _ in range(80):
        if s.state.turn.number >= number and s.state.turn.phase == phase:
            return
        d = decision(s)
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:d.min_choices])
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def test_phasing_out_a_blocker_of_two_attackers_clears_every_block(cards):
    s = table(cards)
    a1 = creature(s, "p1", "Raider", "2/2")
    a2 = creature(s, "p1", "Axe", "3/3")
    wall = creature(s, "p2", "Wall", "3/3", WALL)
    stack = artifact(s, "p2", "Haystack", HAYSTACK)
    automate(s)
    stops(s)
    attack(s, (a1, "p2"), (a2, "p2"))
    passes(s, "p1", "p2")
    block(s, "p2", (wall, a1), (wall, a2))
    assert wall.blocking == a1.id and wall.blocking_more == [a2.id]
    act(s, "p1", type="pass_priority")  # Bob phases his Wall out in the declare blockers step: it leaves combat (702.26b, 506.4)
    mana(s, "p2", 2)
    act(s, "p2", type="activate_ability", card_id=stack.id, ability=0, targets=[wall.id])
    pass_until_stack_empty(s)
    w = s.state.cards[wall.id]
    assert w.zone == "p2:phased" and w.blocking is None and w.blocking_more == []
    check(s)


def test_phasing_out_an_attacker_drops_it_from_a_double_block(cards):
    s = table(cards)
    a1 = creature(s, "p1", "Raider", "2/2")
    a2 = creature(s, "p1", "Axe", "3/3")
    stack = artifact(s, "p1", "Haystack", HAYSTACK)
    wall = creature(s, "p2", "Wall", "3/3", WALL)
    automate(s)
    stops(s)
    attack(s, (a1, "p2"), (a2, "p2"))
    passes(s, "p1", "p2")
    block(s, "p2", (wall, a1), (wall, a2))
    mana(s, "p1", 2)
    act(s, "p1", type="activate_ability", card_id=stack.id, ability=0, targets=[a2.id])
    pass_until_stack_empty(s)
    w = s.state.cards[wall.id]
    assert s.state.cards[a2.id].zone == "p1:phased" and w.blocking == a1.id and w.blocking_more == []
    check(s)


def test_lure_with_menace_needs_both_able_blockers(cards):
    s = table(cards)
    lure = creature(s, "p1", "Taunter", "2/2", f"Menace\n{LURE}")
    a = creature(s, "p2", "Guard", "2/2")
    b = creature(s, "p2", "Spare", "1/1")
    automate(s)
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")  # 509.1c: both can block it together, so both must
    block(s, "p2", (a, lure), (b, lure))
    check(s)


def test_lure_with_menace_and_a_single_able_blocker_requires_nothing(cards):
    s = table(cards)
    lure = creature(s, "p1", "Taunter", "2/2", f"Menace\n{LURE}")
    creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (lure, "p2"))
    block(s, "p2")  # one creature can't block a menace creature alone: no requirement can be obeyed
    check(s)


def test_a_blocker_at_its_limit_must_prefer_a_lure_over_a_plain_attacker(cards):
    s = table(cards)
    l1 = creature(s, "p1", "Taunter", "2/2", LURE)
    l2 = creature(s, "p1", "Decoy", "2/2", LURE)
    plain = creature(s, "p1", "Ogre", "3/3")
    a = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (l1, "p2"), (l2, "p2"), (plain, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (a, plain))  # blocking the Ogre obeys no requirement; blocking either lure would
    block(s, "p2", (a, l2))
    check(s)


def test_extra_blocks_from_a_static_and_an_aura_add_up(cards):
    s = table(cards)
    a1 = creature(s, "p1", "Raider", "2/2")
    a2 = creature(s, "p1", "Axe", "3/3")
    a3 = creature(s, "p1", "Third", "1/1")
    wall = creature(s, "p2", "Wall", "3/3", WALL)
    act(s, "p2", type="create_token", player="p2", token={"name": "Blessing", "type_line": "Token Enchantment — Aura",
                                                          "text": "Enchant creature\nEnchanted creature gets +2/+2, has vigilance, and can block an additional creature each combat."})  # noqa: E501
    aura = next(c for c in s.state.cards.values() if c.name == "Blessing")
    act(s, "p2", type="attach", card_ids=[aura.id], to=wall.id)
    automate(s)
    attack(s, (a1, "p2"), (a2, "p2"), (a3, "p2"))
    block(s, "p2", (wall, a1), (wall, a2), (wall, a3))
    assert s.state.cards[wall.id].blocking_more == [a2.id, a3.id]
    check(s)


def test_trampler_whose_only_blocker_phased_out_tramples_over(cards):
    s = table(cards)
    wurm = creature(s, "p1", "Wurm", "4/4", "Trample")
    ox = creature(s, "p1", "Ox", "4/4")
    g1 = creature(s, "p2", "Guard", "2/2")
    g2 = creature(s, "p2", "Guard 2", "2/2")
    stack = artifact(s, "p2", "Haystack", HAYSTACK)
    stack2 = artifact(s, "p2", "Haystack 2", HAYSTACK)
    automate(s)
    stops(s)
    attack(s, (wurm, "p2"), (ox, "p2"))
    passes(s, "p1", "p2")
    block(s, "p2", (g1, wurm), (g2, ox))
    act(s, "p1", type="pass_priority")
    mana(s, "p2", 4)
    act(s, "p2", type="activate_ability", card_id=stack.id, ability=0, targets=[g1.id])
    pass_until_stack_empty(s)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=stack2.id, ability=0, targets=[g2.id])
    pass_until_stack_empty(s)
    passes(s, "p1", "p2")
    assert decision(s) is None  # (no division to ask for: nothing blocks the Wurm any more)
    assert s.state.players["p2"].life == 36  # 702.19d: all of the trampler's damage; the Ox stays blocked (509.1h): none
    check(s)


def stolen_and_phased_out(cards):
    """Three players; Bob takes Alice's Bear until end of turn and phases it out."""
    s = table(cards, players=3)
    bear = creature(s, "p1", "Bear", "2/2")
    stack = artifact(s, "p2", "Haystack", HAYSTACK)
    thief = artifact(s, "p2", "Thief", THIEF)
    automate(s)
    stops(s)
    attack(s)
    act(s, "p1", type="pass_priority")
    mana(s, "p2", 4)
    act(s, "p2", type="activate_ability", card_id=thief.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].controller == "p2"
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=stack.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].zone == "p2:phased"
    return s, bear


def test_a_leaving_player_s_phased_out_stolen_creature_returns_to_its_owner(cards):
    s, bear = stolen_and_phased_out(cards)
    act(s, "p2", type="concede")
    b = s.state.cards[bear.id]
    assert b.zone == "p1:phased" and b.controller == "p1"  # 800.4a: the control effect ends; 702.26n: it phases in later
    run_to(s, 4)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    check(s)


def test_a_control_effect_ending_while_the_token_is_phased_out(cards):
    s, bear = stolen_and_phased_out(cards)
    run_to(s, 2)
    b = s.state.cards[bear.id]
    # 702.26a: it phases in before Bob untaps; 702.26f: the control effect ended at cleanup, so it is Alice's again
    assert b.zone == "p1:battlefield" and b.controller == "p1" and s.state.rules.control_changed == []
    check(s)


def test_divine_smite_phases_out_or_exiles_a_black_one(cards):
    s = build(cards, mine=("Divine Smite", "Divine Smite"), theirs=("Vampire Nighthawk", "Grizzly Bears"))
    hawk = put(s, "Vampire Nighthawk", "p2")
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Divine Smite")
    add_mana(s, W=1)
    cast(s, "Divine Smite", targets=[hawk.id])
    assert s.state.cards[hawk.id].zone == "p2:exile"
    to_hand(s, "Divine Smite")  # (the other copy)
    add_mana(s, W=1)
    cast(s, "Divine Smite", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p2:phased"
    check(s)


def test_teferis_veil_phases_the_attacker_out_at_end_of_combat(cards):
    s = build(cards, mine=("Teferi's Veil",))
    put(s, "Teferi's Veil")
    bear = token(s, "p1", "Bear", "2/2")
    run_to(s, 3)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    run_to(s, 3, "main2")
    assert s.state.cards[bear.id].zone == "p1:phased" and s.state.players["p2"].life == 38
    run_to(s, 5)
    assert s.state.cards[bear.id].zone == "p1:battlefield"  # 702.26a: her next untap step
    check(s)


def test_goblin_cadets_change_hands_when_they_block(cards):
    s = build(cards, theirs=("Goblin Cadets",))
    cadets = put(s, "Goblin Cadets", "p2")
    ogre = token(s, "p1", "Ogre", "3/3")
    run_to(s, 3)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p2"}])
    for _ in range(10):
        d = decision(s)
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": cadets.id, "attacker_id": ogre.id}])
    run_to(s, 3, "main2")
    c = s.state.cards[cadets.id]
    # 506.4: the control change removes them from combat; the Ogre stays blocked (509.1h) and deals no damage
    assert c.controller == "p1" and s.state.players["p2"].life == 40 and ogre.id in s.state.cards
    check(s)
