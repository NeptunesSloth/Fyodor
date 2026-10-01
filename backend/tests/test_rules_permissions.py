"""Cast / play permissions and cost modifiers (app/rules/permissions.py): "spells you cast cost
{1} less", "spells your opponents cast cost {2} more", the spell's own reductions, kicker and
commander tax in the 601.2f order, casting from the graveyard / exile / the top of the library,
"you may play that card this turn" (400.7h), once-per-turn permissions, flash permissions, and
what casting from the top of the library reveals (401.5)."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.rules_state import CostModifier, Permission
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules import permissions as P
from app.rules.casting import castable, spell_cost
from app.rules.characteristics import Characteristics, parse_abilities
from app.rules.characteristics import of as chars_of
from app.rules.engine import land_play_problem
from app.rules.mana import parse_cost
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, rules, run_until


def build(cards, alice, bob=((10, "Island"),)):
    a = deck(cards, "Krenko, Mob Boss", list(alice))
    b = deck(cards, "Atraxa, Praetors' Voice", list(bob))
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def find(s, name, pid="p1", where=None):
    return next(c for c in s.state.cards.values() if (c.name == name or c.name.startswith(name + " //")) and c.owner == pid
                and (where is None or c.zone.endswith(":" + where)))


def hold(s, pid="p1"):
    """Keep priority after casting, so the spell is still on the stack to look at."""
    act(s, pid, type="set_prefs", hold_priority=True)


def refresh(s):
    """Any rules-engine intent makes the engine look at the table again (what it reveals); a land
    drop from the hand is the least eventful one."""
    forest = put(s, "Forest", "hand")
    act(s, "p1", type="play_land", card_id=forest.id)


def put(s, name, where, pid="p1", position=None):
    card = find(s, name, pid)
    payload = {"type": "move", "card_ids": [card.id], "to": {"player": pid, "zone": where}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[card.id]


def cost_of(s, card, cards, pid="p1", **kw):
    return spell_cost(s.state, card, chars_of(card, cards), info=cards, player=pid, **kw).text()


def hints(s, pid="p1"):
    return s.view(pid)["rules"]["hints"]


# -- cost modifiers (601.2f, 118.7a) ---------------------------------------------------------------
def test_reduction_touches_only_generic_and_never_goes_below_zero(cards):
    s = build(cards, [(1, "Stone Calendar"), (1, "Lightning Bolt"), (1, "Grizzly Bears"), (1, "Sol Ring")])
    put(s, "Stone Calendar", "battlefield")
    bolt, bears, ring = put(s, "Lightning Bolt", "hand"), put(s, "Grizzly Bears", "hand"), put(s, "Sol Ring", "hand")
    assert cost_of(s, bolt, cards) == "{R}"  # {R}: nothing generic to reduce (118.7a)
    assert cost_of(s, bears, cards) == "{G}"  # {1}{G} − 1
    assert cost_of(s, ring, cards) == "{0}"  # {1} − 1 = {0}, not less (601.2f)
    mana(s, G=1)
    assert castable(s.state, "p1", bears, cards) and castable(s.state, "p1", ring, cards)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert s.state.players["p1"].mana_pool.get("G", 0) == 0 if hasattr(s.state.players["p1"], "mana_pool") else True
    replay_matches(s)


def test_typed_reductions_apply_to_matching_spells_only(cards):
    s = build(cards, [(1, "Foundry Inspector"), (1, "Mocking Sprite"), (1, "Ruby Medallion"), (1, "Honest Rutstein"),
                      (1, "Sol Ring"), (1, "Lightning Bolt"), (1, "Grizzly Bears"), (1, "Opt")])
    for name in ("Foundry Inspector", "Mocking Sprite", "Ruby Medallion", "Honest Rutstein"):
        put(s, name, "battlefield")
    ring, bolt, bears, opt = (put(s, n, "hand") for n in ("Sol Ring", "Lightning Bolt", "Grizzly Bears", "Opt"))
    assert cost_of(s, ring, cards) == "{0}"  # artifact: Foundry Inspector
    assert cost_of(s, bolt, cards) == "{R}"  # red instant: Medallion and Sprite both apply, nothing generic to take
    assert cost_of(s, bears, cards) == "{G}"  # creature: Rutstein
    assert cost_of(s, opt, cards) == "{U}"  # instant, not red: Sprite only, nothing generic
    assert cost_of(s, ring, cards, pid="p2") == "{1}"  # "you cast": Bob gets nothing from Alice's Inspector


def test_increases_for_opponents_and_for_everyone(cards):
    s = build(cards, [(1, "God-Pharaoh's Statue"), (1, "Thorn of Amethyst"), (1, "Sol Ring"), (1, "Grizzly Bears")],
              bob=[(1, "Sol Ring"), (1, "Grizzly Bears"), (8, "Island")])
    put(s, "God-Pharaoh's Statue", "battlefield")
    put(s, "Thorn of Amethyst", "battlefield")
    ring, bears = put(s, "Sol Ring", "hand"), put(s, "Grizzly Bears", "hand")
    bob_ring, bob_bears = put(s, "Sol Ring", "hand", pid="p2"), put(s, "Grizzly Bears", "hand", pid="p2")
    assert cost_of(s, ring, cards) == "{2}"  # Thorn: noncreature +1 for its controller too; the Statue is hers
    assert cost_of(s, bears, cards) == "{1}{G}"
    assert cost_of(s, bob_ring, cards, pid="p2") == "{4}"  # +1 Thorn, +2 Statue ("spells your opponents cast")
    assert cost_of(s, bob_bears, cards, pid="p2") == "{3}{G}"


def test_kicker_joins_the_total_before_reductions_and_commander_tax_is_an_increase(cards):
    s = build(cards, [(1, "Stone Calendar"), (1, "Test Kicked Bolt"), (5, "Forest")])
    put(s, "Stone Calendar", "battlefield")
    bolt = put(s, "Test Kicked Bolt", "hand")
    # {R} + kicker {1}{R} = {1}{R}{R}, then −1: the reduction sees the kicked total (601.2f)
    assert cost_of(s, bolt, cards) == "{R}"
    assert cost_of(s, bolt, cards, kicker=1) == "{R}{R}"
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, kicker=1, targets=["p2"])
    pass_until_stack_empty(s)
    assert "paid {R}{R} for Test Kicked Bolt" in json.dumps(s.view("p2")["log"])
    assert s.state.players["p2"].life == 38  # kicked: 2 damage
    krenko = find(s, "Krenko, Mob Boss")
    s.state.players["p1"].commander_tax[krenko.commander_key] = 2  # cast once before
    assert cost_of(s, krenko, cards) == "{3}{R}{R}"  # {2}{R}{R} + 2 tax − 1


def test_stored_cost_modifier_lasts_until_end_of_turn(cards):
    s = build(cards, [(1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "hand")
    rules(s).cost_modifiers.append(CostModifier(id="m1", controller="p1", delta=-1, label="test"))
    assert cost_of(s, bears, cards) == "{G}"
    run_until(s, lambda s: s.state.turn.number == 2)
    assert rules(s).cost_modifiers == []
    assert cost_of(s, bears, cards) == "{1}{G}"


def test_the_spells_own_reductions(cards):
    s = build(cards, [(1, "Hollow Marauder"), (1, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Wizard's Lightning"),
                      (1, "Delver of Secrets"), (1, "Seeds of Renewal"), (1, "Sol Ring")])
    marauder = put(s, "Hollow Marauder", "hand")
    assert cost_of(s, marauder, cards) == "{6}{B}"
    put(s, "Grizzly Bears", "graveyard")
    put(s, "Llanowar Elves", "graveyard")
    put(s, "Sol Ring", "graveyard")  # (not a creature card)
    assert cost_of(s, marauder, cards) == "{4}{B}"  # for each creature card in your graveyard
    lightning = put(s, "Wizard's Lightning", "hand")
    assert cost_of(s, lightning, cards) == "{2}{R}"
    put(s, "Delver of Secrets", "battlefield")  # a Human Wizard
    assert cost_of(s, lightning, cards) == "{R}"  # "if you control a Wizard"
    assert scripts.spell_definition(chars_of(lightning, cards)) is not None  # the cost line doesn't make the spell manual
    seeds = put(s, "Seeds of Renewal", "hand")
    assert cost_of(s, seeds, cards) == "{5}{G}"  # undaunted: one opponent


# -- permissions (601.3, 400.7h/i) -----------------------------------------------------------------
def test_play_lands_from_the_graveyard(cards):
    s = build(cards, [(1, "Ramunap Excavator"), (3, "Forest")])
    forest = put(s, "Forest", "graveyard")
    assert forest.id not in hints(s)["playable_lands"]
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=forest.id)
    put(s, "Ramunap Excavator", "battlefield")
    assert forest.id in hints(s)["playable_lands"]
    act(s, "p1", type="play_land", card_id=forest.id)
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    other = put(s, "Forest", "graveyard")
    assert other.id not in hints(s)["playable_lands"]  # one land per turn still (305.2)
    replay_matches(s)


def test_once_per_turn_cast_from_the_graveyard_with_the_spells_own_reduction(cards):
    s = build(cards, [(1, "Karador, Ghost Chieftain"), (1, "Grizzly Bears"), (1, "Llanowar Elves"), (1, "Sol Ring"), (6, "Forest")])
    karador = put(s, "Karador, Ghost Chieftain", "hand")
    bears, elves, ring = put(s, "Grizzly Bears", "graveyard"), put(s, "Llanowar Elves", "graveyard"), put(s, "Sol Ring", "graveyard")
    assert cost_of(s, karador, cards) == "{3}{W}{B}{G}"  # {5}{W}{B}{G} − 2 creature cards
    mana(s, W=1, B=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=karador.id)
    pass_until_stack_empty(s)
    assert s.state.cards[karador.id].zone == "p1:battlefield"
    mana(s, G=3, C=2)
    h = hints(s)
    assert bears.id in h["castable"] and elves.id in h["castable"] and ring.id not in h["castable"]  # creature spells only
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.view("p2")["cards"][bears.id]["stack_info"]["tags"] == ["Cast from the graveyard"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert elves.id not in hints(s)["castable"]  # once during each of your turns
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=elves.id)
    run_until(s, lambda s: s.state.turn.number == 2)
    mana(s, G=1)
    assert not castable(s.state, "p1", elves, cards, check_priority=False)  # not during Bob's turn
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    mana(s, G=1)
    assert castable(s.state, "p1", elves, cards, check_priority=False)  # a new turn of hers
    replay_matches(s)


def test_you_may_play_that_card_this_turn_follows_the_object(cards):
    s = build(cards, [(1, "Abbot of Keral Keep"), (1, "Lightning Bolt"), (1, "Grizzly Bears"), (4, "Forest")])
    abbot = put(s, "Abbot of Keral Keep", "hand")
    bolt = put(s, "Lightning Bolt", "library", position="top")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=abbot.id)
    pass_until_stack_empty(s)  # the creature, then its enters trigger
    assert s.state.cards[bolt.id].zone == "p1:exile"
    perms = rules(s).permissions
    assert len(perms) == 1 and perms[0].card == bolt.id and perms[0].object_id == rules(s).object_id(bolt.id)
    mana(s, R=1)
    assert bolt.id in hints(s)["castable"]
    # 400.7: bounced to the hand by hand and exiled again, it is a new object: the permission was for the old one
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "exile"})
    assert bolt.id not in hints(s)["castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])


def test_exiled_card_cast_from_exile_and_the_permission_ends_with_the_turn(cards):
    s = build(cards, [(1, "Abbot of Keral Keep"), (1, "Lightning Bolt"), (1, "Grizzly Bears"), (4, "Forest")])
    abbot = put(s, "Abbot of Keral Keep", "hand")
    bears = put(s, "Grizzly Bears", "library", position="top")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=abbot.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    mana(s, G=1, C=1)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.view("p2")["cards"][bears.id]["stack_info"]["tags"] == ["Cast from exile"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert rules(s).permissions == []  # spent: the card on the stack was a new object (400.7)
    replay_matches(s)
    # a land exiled this way may be played (701.13: "play" covers both)
    s2 = build(cards, [(1, "Abbot of Keral Keep"), (1, "Lightning Bolt"), (4, "Forest")])
    abbot = put(s2, "Abbot of Keral Keep", "hand")
    forest = put(s2, "Forest", "library", position="top")
    mana(s2, R=1, C=1)
    act(s2, "p1", type="cast_spell", card_id=abbot.id)
    pass_until_stack_empty(s2)
    assert forest.id in hints(s2)["playable_lands"]
    run_until(s2, lambda s: s.state.turn.number == 2)
    assert rules(s2).permissions == []  # "this turn" ended in the cleanup step (514.2)
    assert land_play_problem(s2.state, "p1", s2.state.cards[forest.id], chars_of(forest, cards), info=cards) == \
        "You can only play lands from your hand"


def test_until_the_end_of_your_next_turn(cards):
    s = build(cards, [(1, "Blazing Crescendo"), (1, "Grizzly Bears"), (1, "Sol Ring"), (4, "Forest")])
    bears = put(s, "Grizzly Bears", "battlefield")
    crescendo = put(s, "Blazing Crescendo", "hand")
    ring = put(s, "Sol Ring", "library", position="top")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=crescendo.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].zone == "p1:exile"
    assert rules(s).permissions[0].until == "end_of_next_turn"
    run_until(s, lambda s: s.state.turn.number == 2)  # Bob's turn: still granted
    assert len(rules(s).permissions) == 1
    run_until(s, lambda s: s.state.turn.number == 3)  # Alice's next turn: still granted …
    mana(s, C=1)
    assert ring.id in hints(s)["castable"]
    run_until(s, lambda s: s.state.turn.number == 4)  # … and gone after it
    assert rules(s).permissions == []
    replay_matches(s)


def test_zone_permission_from_a_spell_ends_with_the_turn(cards):
    s = build(cards, [(1, "Test Grave Recall"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (2, "Forest")])
    recall = put(s, "Test Grave Recall", "hand")
    bears, bolt, forest = put(s, "Grizzly Bears", "graveyard"), put(s, "Lightning Bolt", "graveyard"), put(s, "Forest", "graveyard")
    mana(s, B=1, G=1, C=1, R=1)
    assert bears.id not in hints(s)["castable"]
    act(s, "p1", type="cast_spell", card_id=recall.id)
    pass_until_stack_empty(s)
    h = hints(s)
    assert bears.id in h["castable"] and bolt.id in h["castable"] and forest.id in h["playable_lands"]
    act(s, "p1", type="play_land", card_id=forest.id)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:battlefield"
    run_until(s, lambda s: s.state.turn.number == 2)
    assert rules(s).permissions == []
    replay_matches(s)


def test_flash_permission_changes_timing_only(cards):
    s = build(cards, [(1, "Shimmer Myr"), (1, "Sol Ring"), (1, "Grizzly Bears")])
    put(s, "Shimmer Myr", "battlefield")
    ring, bears = put(s, "Sol Ring", "hand"), put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="set_prefs", response="on")  # stop at every priority
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    mana(s, C=1, G=1)
    act(s, "p2", type="pass_priority")
    assert rules(s).priority == "p1"
    h = hints(s)
    assert ring.id in h["castable"] and bears.id not in h["castable"]  # artifact spells as though they had flash
    hold(s)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    assert s.state.cards[ring.id].zone == "stack"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)


def test_free_permission_is_an_alternative_cost_and_kicker_is_still_paid(cards):
    s = build(cards, [(1, "Test Kicked Bolt"), (1, "Thorn of Amethyst"), (5, "Forest")])
    bolt = put(s, "Test Kicked Bolt", "hand")
    rules(s).permissions.append(Permission(id="p", player="p1", cast=True, zone="hand", free=True, label="test"))
    assert cost_of(s, bolt, cards, free=True) == "{0}"
    assert cost_of(s, bolt, cards, free=True, kicker=1) == "{1}{R}"  # 118.9d: the additional cost still applies
    put(s, "Thorn of Amethyst", "battlefield")
    assert cost_of(s, bolt, cards, free=True, kicker=1) == "{2}{R}"  # and so does an increase
    mana(s, R=1, C=2)
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, kicker=1, targets=["p2"])
    record = rules(s).payments[rules(s).object_id(bolt.id)]
    assert record.alternative == "free" and record.kicked == 1 and record.total_cost == "{2}{R}"
    assert s.view("p2")["cards"][bolt.id]["stack_info"]["tags"] == ["Cast from the hand without paying its mana cost", "Kicked"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38  # kicked: 2 damage (and Alice drew)


def test_cascade_free_cast_still_pays_an_increase(cards):
    s = build(cards, [(1, "Bloodbraid Elf"), (1, "Lightning Bolt"), (1, "Thorn of Amethyst"), (8, "Forest")])
    put(s, "Thorn of Amethyst", "battlefield")
    elf = put(s, "Bloodbraid Elf", "hand")
    put(s, "Lightning Bolt", "library", position="top")
    mana(s, R=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    run_until(s, lambda s: rules(s).decision is not None and "Cascade" in rules(s).decision.prompt)
    act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["yes"])
    act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["p2"])
    run_until(s, lambda s: not s.state.zones.get("stack"))
    assert "paid {1} for Lightning Bolt" in json.dumps(s.view("p2")["log"])  # 118.9d: Thorn's increase on a {0} cost
    assert s.state.players["p2"].life == 37


# -- the top of the library (401.5) ------------------------------------------------------------------
def test_casting_from_the_top_of_the_library_reveals_only_what_the_card_says(cards):
    s = build(cards, [(1, "Garruk's Horde"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (1, "Llanowar Elves"), (4, "Forest")])
    bears = put(s, "Grizzly Bears", "library", position="top")
    assert s.view("p2")["zones"]["p1:library"]["known"] == []
    put(s, "Garruk's Horde", "battlefield")
    refresh(s)
    assert s.view("p2")["zones"]["p1:library"]["known"] == [[0, bears.id]]  # "play with the top card revealed"
    assert s.view("p2")["cards"][bears.id]["name"] == "Grizzly Bears"
    mana(s, G=1, C=1)
    assert bears.id in hints(s)["castable"]
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    top = s.state.zones["p1:library"][0]
    assert s.view("p2")["zones"]["p1:library"]["known"] == [[0, top]]  # the new top card is revealed now
    assert s.state.cards[top].name != "Grizzly Bears"
    bolt = put(s, "Lightning Bolt", "library", position="top")
    mana(s, R=1)
    assert bolt.id not in hints(s)["castable"]  # creature spells only
    # the Horde leaves by hand: the top card is hidden again at once (no engine action needed)
    act(s, "p1", type="move", card_ids=[find(s, "Garruk's Horde").id], to={"player": "p1", "zone": "graveyard"})
    assert s.view("p2")["zones"]["p1:library"]["known"] == []
    replay_matches(s)


def test_a_reveal_source_taken_by_hand_reveals_its_new_controllers_library(cards):
    """The view derives what is revealed from the table (401.5): Garruk's Horde moved to Bob's
    side by hand stops revealing Alice's top card and reveals Bob's at once — on every action,
    and after the history is rebuilt."""
    s = build(cards, [(1, "Garruk's Horde"), (1, "Grizzly Bears"), (4, "Forest")], bob=[(1, "Llanowar Elves"), (9, "Island")])
    bears = put(s, "Grizzly Bears", "library", position="top")
    elves = put(s, "Llanowar Elves", "library", pid="p2", position="top")
    horde = put(s, "Garruk's Horde", "battlefield")
    assert s.view("p2")["zones"]["p1:library"]["known"] == [[0, bears.id]]
    assert s.view("p1")["zones"]["p2:library"]["known"] == []
    act(s, "p2", type="set_controller", card_ids=[horde.id], player="p2")  # taken by hand (no engine intent)
    assert s.state.cards[horde.id].controller == "p2"
    assert s.view("p2")["zones"]["p1:library"]["known"] == []  # Alice's top card is hidden again
    assert s.view("__spectator__")["zones"]["p1:library"]["known"] == []
    assert s.view("p1")["zones"]["p2:library"]["known"] == [[0, elves.id]]  # and Bob's is revealed
    assert s.view("p1")["cards"][elves.id]["name"] == "Llanowar Elves"
    rebuilt = s.history.rebuild()
    from app.game.views import build_view

    assert build_view(rebuilt, "p1")["zones"]["p2:library"]["known"] == [[0, elves.id]]
    assert build_view(rebuilt, "p2")["zones"]["p1:library"]["known"] == []
    # Bob may now cast creature spells from the top of his library (the Horde's other ability)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    mana(s, pid="p2", G=1)
    assert elves.id in hints(s, "p2")["castable"]
    act(s, "p2", type="cast_spell", card_id=elves.id)
    pass_until_stack_empty(s)
    assert s.state.cards[elves.id].zone == "p2:battlefield"
    # a "you may look" source taken by hand: only its new controller sees their own top card
    s2 = build(cards, [(1, "Test Oracle Lens"), (1, "Grizzly Bears"), (4, "Forest")], bob=[(1, "Llanowar Elves"), (9, "Island")])
    bears = put(s2, "Grizzly Bears", "library", position="top")
    elves = put(s2, "Llanowar Elves", "library", pid="p2", position="top")
    lens = put(s2, "Test Oracle Lens", "battlefield")
    assert s2.view("p1")["zones"]["p1:library"]["known"] == [[0, bears.id]]
    act(s2, "p2", type="set_controller", card_ids=[lens.id], player="p2")
    assert s2.view("p1")["zones"]["p1:library"]["known"] == []
    assert s2.view("p2")["zones"]["p2:library"]["known"] == [[0, elves.id]]
    assert s2.view("p1")["zones"]["p2:library"]["known"] == []
    assert s2.view("__spectator__")["zones"]["p2:library"]["known"] == []
    replay_matches(s)
    replay_matches(s2)


def test_look_at_the_top_card_any_time_is_private(cards):
    s = build(cards, [(1, "Test Oracle Lens"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (4, "Forest")])
    bears = put(s, "Grizzly Bears", "library", position="top")
    put(s, "Test Oracle Lens", "battlefield")
    assert bears.id not in hints(s)["castable"]  # not visible yet: the engine hasn't looked at the table
    refresh(s)
    assert s.view("p1")["zones"]["p1:library"]["known"] == [[0, bears.id]]
    assert s.view("p2")["zones"]["p1:library"]["known"] == []  # only you may look
    assert s.view("__spectator__")["zones"]["p1:library"]["known"] == []
    mana(s, G=1, C=1)
    assert bears.id in hints(s)["castable"]
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.view("p2")["cards"][bears.id]["name"] == "Grizzly Bears"  # public on the stack
    assert s.view("p2")["cards"][bears.id]["stack_info"]["tags"] == ["Cast from the library"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    replay_matches(s)


def test_play_lands_from_the_top_of_the_library(cards):
    s = build(cards, [(1, "Courser of Kruphix"), (1, "Grizzly Bears"), (4, "Forest")])
    forest = put(s, "Forest", "library", position="top")
    assert s.view("p2")["zones"]["p1:library"]["known"] == []
    put(s, "Courser of Kruphix", "battlefield")
    # placed by hand: the view reads the table — revealed at once, no engine action in between
    assert s.view("p2")["zones"]["p1:library"]["known"] == [[0, forest.id]]
    assert forest.id in hints(s)["playable_lands"]
    mana(s, G=1, C=1)
    bears = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="cast_spell", card_id=bears.id)
    pass_until_stack_empty(s)
    assert s.view("p2")["zones"]["p1:library"]["known"] == [[0, forest.id]]
    assert forest.id in hints(s)["playable_lands"]
    act(s, "p1", type="play_land", card_id=forest.id)
    assert s.state.cards[forest.id].zone == "p1:battlefield"
    pass_until_stack_empty(s)  # landfall
    assert s.state.players["p1"].life == 41
    replay_matches(s)


# -- the grammar --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Spells you cast cost {1} less to cast.", {"delta": -1, "caster": "you", "filter": None}),
    ("Creature spells you cast cost {2} less to cast.", {"delta": -2, "caster": "you"}),
    ("Spells your opponents cast cost {1} more to cast.", {"delta": 1, "caster": "opponent"}),
    ("Noncreature spells cost {1} more to cast.", {"delta": 1, "caster": "any"}),
    ("Aura spells you cast cost {1} less to cast.", {"delta": -1}),
    ("Legendary spells you cast cost {1} less to cast.", {"delta": -1}),
])
def test_cost_modifier_wordings(text, expected):
    d = P.define_static(text, "static")
    assert d is not None and d["static"] == "cost_modifier"
    for k, v in expected.items():
        assert d[k] == v


@pytest.mark.parametrize("text", [
    # each of these means something the engine doesn't model: refused, never guessed
    "Once during each of your turns, you may cast an instant or sorcery spell from your graveyard. If a spell cast this way would be put into your graveyard, exile it instead.",
    "Spells you cast from anywhere other than your hand cost {1} less to cast.",
    "During each of your turns, you may play a land and cast a permanent spell of each permanent type from your graveyard.",
    "The first creature spell you cast each turn costs {1} less to cast.",
    "Spells your opponents cast that target this creature cost {1} more to cast.",
    "This spell costs {1} less to cast for each creature in your party.",
    "This spell costs {1} less to cast if it targets a tapped creature.",
    "Equip abilities you activate cost {1} less to activate.",
    "You may cast spells from the top of your library. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.",
])
def test_wordings_the_grammar_refuses(text):
    assert P.define_static(text, "static") is None
    assert P.define_static(text, "spell") is None


def test_effect_wordings():
    assert P.parse_clause("exile the top card of your library") is None  # (the library grammar's: app/rules/language.py)
    granted = P.parse_clause("until the end of your next turn, you may play those cards")
    assert granted is not None and granted[0][0]["until"] == "end_of_next_turn" and granted[0][0]["play"]
    assert granted[0][0]["who"] == "them:card"  # a pronoun: bound by scripts.resolve_it to what was exiled
    cast_only = P.parse_clause("until end of turn, you may cast that card")
    assert cast_only is not None and cast_only[0][0]["play"] is False and cast_only[0][0]["cast"]
    assert P.parse_clause("you may play that card this turn")[0][0] == {
        "do": "grant_play", "who": "it:card", "play": True, "cast": True, "until": "end_of_turn", "optional": True}
    assert P.parse_clause("until end of turn, you may play that card this turn") is None
    assert P.parse_clause("you may play that card until your next end step") is None
    # a bare "you may cast that card": cast it as this resolves, ignoring timing — not a permission
    # that lasts the turn (Chandra, Torch of Defiance's wording): refused, never a turn-long grant
    assert P.parse_clause("you may cast that card") is None
    assert P.parse_clause("you may play it") is None


def test_that_card_binds_to_what_the_ability_moved_or_stays_manual():
    """"You may play that card / it": the object an earlier instruction of the same ability
    exiled — found where it went (400.7h/j) — never a guess at "the top card"."""
    top = scripts.parse_effects("Exile the top card of your library. Until end of turn, you may play that card.", it="self")
    assert top is not None
    exiled, grant = top[0]
    assert exiled["do"] == "exile_top" and exiled["as"] == "e0" and grant == {
        "do": "grant_play", "who": "ref:e0", "play": True, "cast": True, "until": "end_of_turn", "optional": True}
    two = scripts.parse_effects("Exile the top two cards of your library. You may play those cards this turn.")
    assert two is not None and two[0][1]["who"] == "ref:e0"
    from_grave = scripts.parse_effects("Exile target card from a graveyard. You may play it this turn.")
    assert from_grave is not None and from_grave[0][0]["do"] == "exile" and from_grave[0][1]["who"] == "ref:e0"
    # number: one card exiled, "those cards" — not the same thing
    assert scripts.parse_effects("Exile the top card of your library. You may play those cards this turn.") is None
    # nothing was moved into a public zone before the grant: manual, never FULL-and-no-op
    assert scripts.parse_effects("Draw a card. You may play it this turn.") is None  # (the hand is hidden, 400.7)
    assert scripts.parse_effects("Draw a card. You may play it this turn.", it="self") is None  # (not the source either)
    assert scripts.parse_effects("You may play that card this turn.") is None
    assert scripts.parse_effects("Tap target creature. You may play it this turn.") is None  # (not moved anywhere)
    assert scripts.parse_effects("Exile the top card of your library. You may cast that card.") is None  # (no duration)
    # Ragavan, Nimble Pilferer: a token the same sentence created is not "that card" (111.1), so
    # the exiled card is the only candidate
    ragavan = scripts.parse_effects("Create a Treasure token and exile the top card of that player's library. "
                                    "Until end of turn, you may cast that card.")
    assert ragavan is not None and [e["do"] for e in ragavan[0]] == ["create_token", "exile_top", "grant_play"]
    assert ragavan[0][1]["as"] == "e1" and ragavan[0][2]["who"] == "ref:e1"
    assert scripts.parse_effects("Create a Treasure token. You may play that card this turn.") is None
    trigger = "When this creature enters, draw a card. You may play it this turn."
    ch = Characteristics(name="X", types=frozenset({"Creature"}), oracle_text=trigger, abilities=tuple(parse_abilities(trigger)))
    assert scripts.definitions(ch) == {}
    assert coverage.of_characteristics(ch).level != "FULL"


def test_play_the_card_exiled_from_a_graveyard_this_turn(cards):
    """"Exile target card from a graveyard. You may play it this turn." grants the new object in
    exile (400.7j), for its controller — and only that object."""
    s = build(cards, [(1, "Test Grave Pilfer"), (1, "Grizzly Bears"), (1, "Lightning Bolt"), (4, "Forest")])
    pilfer = put(s, "Test Grave Pilfer", "hand")
    bears, bolt = put(s, "Grizzly Bears", "graveyard"), put(s, "Lightning Bolt", "graveyard")
    assert coverage.of_characteristics(chars_of(pilfer, cards)).level == "FULL"
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=pilfer.id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    perms = rules(s).permissions
    assert len(perms) == 1 and perms[0].card == bears.id and perms[0].object_id == rules(s).object_id(bears.id)
    mana(s, G=1, C=1, R=1)
    h = hints(s)
    assert bears.id in h["castable"] and bolt.id not in h["castable"]
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.view("p2")["cards"][bears.id]["stack_info"]["tags"] == ["Cast from exile"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and rules(s).permissions == []
    replay_matches(s)


def test_top_of_library_permission_needs_a_reveal_or_look_line():
    """"You may cast creature spells from the top of your library" is only offered for a card the
    player can see (401.5): without a reveal / look line on the same card it could never be used —
    refused at define time rather than claimed as automated."""
    line = "You may cast creature spells from the top of your library."
    assert P.define_static(line, "static") is None
    assert P.define_static(line, "static", (line, "Flying.")) is None
    with_reveal = P.define_static(line, "static", ("Play with the top card of your library revealed.", line))
    assert with_reveal is not None and with_reveal["zone"] == "library_top"
    with_look = P.define_static(line, "static", (line, "You may look at the top card of your library any time."))
    assert with_look is not None and with_look["zone"] == "library_top"
    text = "You may cast creature spells from the top of your library."
    ch = Characteristics(name="Lone", types=frozenset({"Creature"}), oracle_text=text, abilities=tuple(parse_abilities(text)))
    assert scripts.definitions(ch) == {} and coverage.of_characteristics(ch).level != "FULL"


def test_free_permission_is_never_applied_to_a_plain_cast(cards):
    """118.9b: an alternative cost is optional. A "without paying its mana cost" permission is
    used only when the caster opts in (``free``): a plain cast with no paid way is refused, not
    silently made free."""
    s = build(cards, [(1, "Grizzly Bears"), (4, "Forest")])
    bears = put(s, "Grizzly Bears", "exile")
    rules(s).permissions.append(Permission(id="p", player="p1", cast=True, zone="exile", free=True, label="test"))
    mana(s, G=1, C=1)  # (she could pay: still no paid way to cast from exile)
    assert not castable(s.state, "p1", bears, cards)
    assert bears.id not in hints(s)["castable"]
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.state.cards[bears.id].zone == "p1:exile" and rules(s).payments == {}
    hold(s)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)
    record = rules(s).payments[rules(s).object_id(bears.id)]
    assert record.alternative == "free" and record.total_cost == "{0}"
    assert s.view("p2")["cards"][bears.id]["stack_info"]["tags"] == ["Cast from exile without paying its mana cost"]
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)


def test_parse_cost_helper_sanity():
    assert parse_cost("{2}{R}").plus_generic(-5).generic == -3  # (the pipeline clamps; the type doesn't)
    assert zone  # (helper import used by other tests)
