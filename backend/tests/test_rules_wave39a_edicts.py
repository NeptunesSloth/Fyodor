"""Wave 39A: edicts, "any player may", and pumps counted by blockers, on real Oracle text (tests/fixtures/wave39a_cards.json, from data/cards.sqlite),
researched against CR 2026-09-25. Every scenario checks the replay and a save and a load.

* 101.4, 608.2e: several players choosing — the active player first, then each other player in turn order, each told the earlier choices (101.4b); then
  the action happens to everything chosen at once (Zodiark, Umbral God; Vile Mutilator; the rulings of both).
* 701.21a: the player sacrificing chooses; 107.1a "half … rounded down / up" is counted for each player on their own (Zodiark, Lord Xander, Rakdos the
  Defiler); 701.9a: "discards half the cards in their hand" is the discarding player's own, private choice.
* 118.12, 608.2d: "any player may sacrifice … If a player does, …" (Clackbridge Troll, Brain Gorgers) asks every player in turn order, the choices
  first, then what follows happens once; "target opponent may sacrifice … If they don't, you draw" (Rakdos, Patron of Chaos).
* 509.3d, 608.2h: "for each creature blocking it" counts the blockers as the ability resolves (General Marhault Elsdragon).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import card_named, check, mana, pt
from tests.wave36a_kit import attack_as, block, ready, to_turn_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave39a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w39a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
NAMES = ["Alice", "Bob", "Carol", "Dave"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pod(cards, *decks):
    """One player per deck (Alice, Bob, Carol, Dave): each deck is a list of card names (one of each; ``(n, name)`` for more) and 30 Forests,
    rules automation on, Alice's first main phase."""
    setups = []
    for i, d in enumerate(decks):
        spells = [x if isinstance(x, tuple) else (1, x) for x in d]
        setups.append(PlayerSetup(NAMES[i], cards=deck(cards, "Krenko, Mob Boss" if i == 0 else "Atraxa, Praetors' Voice", [*spells, (30, "Forest")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def all_named(s, name, pid):
    return sorted((c for c in s.state.cards.values() if c.name == name and c.owner == pid), key=lambda c: c.id)


def put(s, name, pid="p1", n=0):
    """The ``n``-th card of that name the player owns, onto the battlefield (a table move: nothing enters, nothing triggers)."""
    c = all_named(s, name, pid)[n]
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_hand(s, name, pid="p1", n=0):
    c = all_named(s, name, pid)[n]
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def cast_from_hand(s, name, pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    return c


def on_battlefield(s, c):
    return c.id in s.state.cards and s.state.cards[c.id].zone.endswith(":battlefield")


def choose(s, option_ids=None, labels=None):
    d = s.state.rules.decision
    ids = option_ids if option_ids is not None else [next(o.id for o in d.options if o.label == lab) for lab in labels]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def sees_only_who(s, observer, chooser_name):
    """The other players' view of a pending choice is the public fact alone (app/rules/view.py): who is choosing, nothing of the options."""
    d = s.view(observer)["rules"]["decision"]
    assert d["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": chooser_name}
    assert d["kind"] == "waiting" and "options" not in d and d["source_id"] is None and "display" not in d


def reload_mid_decision(s):
    """The table rebuilt from its history while a choice is pending: the same decision is still there."""
    again = GameSession(s.history.rebuild(), cards=s.cards)
    assert again.state.rules.decision is not None
    assert again.state.rules.decision.model_dump() == s.state.rules.decision.model_dump()
    return again


# == the cards are FULL ==
@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


# == Zodiark, Umbral God: four players, half of what each controls, in turn order ==
def test_zodiark_four_players_choose_in_turn_order_and_sacrifice_together(cards):
    """Alice 3 non-God creatures (half rounded down: 1), Bob 4 (2), Carol 1 (0: no choice), Dave 2 (1). Alice chooses first (101.4), then Bob who is told her
    choice (101.4b), Carol is skipped, then Dave; nothing is sacrificed until the last choice, then everything at once. Zodiark is a God: it is not counted."""
    s = pod(cards, ["Zodiark, Umbral God", (3, "Grizzly Bears")], [(4, "Llanowar Elves")], [(1, "Young Wolf")], [(2, "Grizzly Bears")])
    mine = [put(s, "Grizzly Bears", "p1", i) for i in range(3)]
    bobs = [put(s, "Llanowar Elves", "p2", i) for i in range(4)]
    carols = [put(s, "Young Wolf", "p3")]
    daves = [put(s, "Grizzly Bears", "p4", i) for i in range(2)]
    mana(s, B=5)
    cast_from_hand(s, "Zodiark, Umbral God")
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (1, 1)
    assert {o.id for o in d.options} == {c.id for c in mine}  # not Zodiark (a God)
    for observer in ("p2", "p3", "p4"):
        sees_only_who(s, observer, "Alice")
    again = reload_mid_decision(s)
    choose(again, [mine[0].id])  # (the reloaded table goes on the same way)
    assert again.state.rules.decision.player == "p2"
    choose(s, [mine[0].id])
    d = s.state.rules.decision
    assert d.player == "p2" and (d.min_choices, d.max_choices) == (2, 2) and {o.id for o in d.options} == {c.id for c in bobs}
    assert "Grizzly Bears" in d.prompt  # Bob knows what Alice chose (101.4b)
    assert on_battlefield(s, mine[0])  # not sacrificed yet (101.4)
    for observer in ("p1", "p3", "p4"):
        sees_only_who(s, observer, "Bob")
    choose(s, [bobs[0].id, bobs[3].id])
    d = s.state.rules.decision
    assert d.player == "p4" and (d.min_choices, d.max_choices) == (1, 1)  # Carol's one creature: half is 0, so no choice and nothing happens to it
    assert on_battlefield(s, bobs[0]) and on_battlefield(s, mine[0])
    choose(s, [daves[1].id])
    settle(s)
    assert [on_battlefield(s, c) for c in mine] == [False, True, True]
    assert [on_battlefield(s, c) for c in bobs] == [False, True, True, False]
    assert on_battlefield(s, carols[0]) and [on_battlefield(s, c) for c in daves] == [True, False]
    assert on_battlefield(s, card_named(s, "Zodiark, Umbral God"))
    check(s)


def settle_combat(s, limit=40):
    """Like ``settle`` but a declaration of blockers is answered with no blocks (and the damage step is played through)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def settle_until_asked(s, limit=30):
    """Let the stack resolve until a choice comes up (not answering it)."""
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never asked")


# == Lord Xander, the Collector: "discards half the cards in their hand, rounded down" is a private choice ==
def test_lord_xander_the_target_opponent_discards_half_their_hand_by_their_own_private_choice(cards):
    s = pod(cards, ["Lord Xander, the Collector"], ["Opt", "Pyroblast", "Murder", "Giant Growth", "Lightning Bolt"], ["Swords to Plowshares"])
    for n in ("Opt", "Pyroblast", "Murder", "Giant Growth", "Lightning Bolt"):
        to_hand(s, n, "p2")
    carols = to_hand(s, "Swords to Plowshares", "p3")
    mana(s, U=1, B=1, R=1, C=4)
    cast_from_hand(s, "Lord Xander, the Collector")
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_one" and sorted(o.label for o in d.options) == ["Bob", "Carol"]
    choose(s, labels=["Bob"])
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (2, 2)  # 5 cards: half rounded down is 2, Bob chooses
    assert sorted(o.label for o in d.options) == ["Giant Growth", "Lightning Bolt", "Murder", "Opt", "Pyroblast"]
    for observer in ("p1", "p3"):  # nobody else sees the hand or the question (701.9a: a private choice)
        sees_only_who(s, observer, "Bob")
        assert not any(n in json.dumps(s.view(observer)["rules"]["decision"]) for n in ("Murder", "Opt", "Pyroblast"))
    again = reload_mid_decision(s)
    choose(again, labels=["Opt", "Murder"])
    settle(again)
    assert sorted(c.name for c in again.state.cards.values() if c.zone == "p2:graveyard") == ["Murder", "Opt"]
    choose(s, labels=["Opt", "Murder"])
    settle(s)
    assert sorted(c.name for c in s.state.cards.values() if c.zone == "p2:graveyard") == ["Murder", "Opt"]
    assert len(s.state.zones["p2:hand"]) == 3 and s.state.cards[carols.id].zone == "p3:hand"
    check(s)


# == Deep-Cavern Bat: a look at a hand is private; the card exiled is public and comes back when the Bat leaves ==
def test_deep_cavern_bat_looks_at_the_hand_privately_and_exiles_a_nonland_card_until_it_leaves(cards):
    s = pod(cards, ["Deep-Cavern Bat", "Lightning Bolt"], ["Opt", "Murder", "Giant Growth"], ["Swords to Plowshares"])
    for n in ("Opt", "Murder", "Giant Growth"):
        to_hand(s, n, "p2")
    act(s, "p2", type="move", card_ids=[all_named(s, "Forest", "p2")[0].id], to={"zone": "hand"})
    to_hand(s, "Swords to Plowshares", "p3")
    mana(s, B=1, C=1)
    bat = cast_from_hand(s, "Deep-Cavern Bat")
    settle_until_asked(s)
    choose(s, labels=["Bob"])
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (0, 1)  # "you may"
    assert sorted(o.label for o in d.options) == ["Giant Growth", "Murder", "Opt"]  # no Forest: a nonland card
    assert "Murder" in json.dumps(s.view("p1"))  # Alice looks
    assert "Murder" not in json.dumps(s.view("p3")) and "Giant Growth" not in json.dumps(s.view("p3"))  # nobody else does
    sees_only_who(s, "p3", "Alice")
    reload_mid_decision(s)
    choose(s, labels=["Murder"])
    settle(s)
    murder = all_named(s, "Murder", "p2")[0]
    assert s.state.cards[murder.id].zone == "p2:exile"  # public now
    assert "Murder" in json.dumps(s.view("p3")) and "Giant Growth" not in json.dumps(s.view("p3"))
    mana(s, R=1)  # Lightning Bolt kills the Bat (1/1): the exile ends, 610.3
    cast_from_hand(s, "Lightning Bolt", targets=[bat.id])
    settle(s)
    assert s.state.cards[bat.id].zone == "p1:graveyard"
    assert s.state.cards[all_named(s, "Murder", "p2")[0].id].zone == "p2:hand"  # 610.3: back in Bob's hand
    check(s)


# == General Marhault Elsdragon: the number of blockers is read as the ability resolves ==
@pytest.mark.parametrize(("one_leaves", "expected"), [(False, (8, 8)), (True, (5, 5))])
def test_marhault_counts_the_creatures_blocking_it_as_the_ability_resolves(cards, one_leaves, expected):
    """Grizzly Bears (2/2) is blocked by two creatures: +3/+3 for each (8/8). If one of them dies with the trigger on the stack (Bob answers with Lightning
    Bolt on his own Llanowar Elves), only the one still blocking counts (the 2022 ruling: "determined as the ability resolves") — the same trigger, a
    different count."""
    s = pod(cards, ["General Marhault Elsdragon", "Grizzly Bears"], ["Llanowar Elves", "Young Wolf", "Lightning Bolt", "Mountain"])
    put(s, "General Marhault Elsdragon")
    bears = put(s, "Grizzly Bears")
    elves, wolf = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    put(s, "Mountain", "p2")  # (Bob can answer: so the trigger waits on the stack)
    ready(s, "Grizzly Bears")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    attack_as(s, "p1", [bears], "p2")
    block(s, "p2", (elves, bears), (wolf, bears))
    assert len(s.state.zones["stack"]) == 1  # the trigger of "a creature you control becomes blocked" (once, however many block it)
    assert pt(s, "Grizzly Bears") == (2, 2)
    if s.state.rules.priority == "p1":  # (Alice has nothing to do with it)
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    if one_leaves:
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[elves.id])
    settle(s)
    assert (s.state.cards[elves.id].zone == "p2:graveyard") == one_leaves
    assert pt(s, "Grizzly Bears") == expected
    check(s)


@pytest.mark.parametrize("name", ["Berserk Murlodont", "Spined Sliver"])
def test_a_beast_or_sliver_blocked_by_two_gets_plus_one_for_each(cards, name):
    """The same count for the other cards that say it of "it" / "that Sliver" (not the source itself)."""
    s = pod(cards, [name], ["Llanowar Elves", "Young Wolf"])
    attacker = put(s, name)
    elves, wolf = put(s, "Llanowar Elves", "p2"), put(s, "Young Wolf", "p2")
    ready(s, name)
    base = pt(s, name)
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    attack_as(s, "p1", [attacker], "p2")
    block(s, "p2", (elves, attacker), (wolf, attacker))
    settle(s)
    assert pt(s, name) == (base[0] + 2, base[1] + 2)
    check(s)


# == Clackbridge Troll / Brain Gorgers: "any opponent / player may sacrifice a creature of their choice. If a player does, …" ==
def play_through(s, phase, pays=None, limit=60):
    """Pass priority to ``phase``; "pay …?" questions are answered from ``pays`` (player id -> yes or no), a choice of what to sacrifice takes the first."""
    pays = pays or {}
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == phase and not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and d.prompt.endswith("?"):
            want = "Pay" if pays.get(d.player) else "Don't"
            choose(s, [next(o.id for o in d.options if o.label.startswith(want))])
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError(f"never reached {phase}")


@pytest.mark.parametrize(("bob", "carol"), [(True, False), (True, True), (False, True), (False, False)])
def test_clackbridge_troll_every_opponent_is_asked_and_what_follows_happens_once(cards, bob, carol):
    """The 2019 ruling: the next opponent in turn order chooses whether to sacrifice (and what), then each other opponent does the same; then all chosen
    creatures are sacrificed at the same time. If one or more were sacrificed, the Troll taps, Alice gains 3 life and draws a card — not more for a second."""
    s = pod(cards, ["Clackbridge Troll"], [(2, "Grizzly Bears")], [(2, "Llanowar Elves")])
    troll = put(s, "Clackbridge Troll")
    bears, elves = [put(s, "Grizzly Bears", "p2", i) for i in range(2)], [put(s, "Llanowar Elves", "p3", i) for i in range(2)]
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "begin_combat", "main2"])
    life, hand = s.state.players["p1"].life, len(s.state.zones["p1:hand"])
    while s.state.rules.decision is None:  # to Bob's question
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_one"  # the next player in turn order after Alice
    assert d.prompt.endswith("?") and [o.label for o in d.options] == ["Pay Sacrifice a creature", "Don't pay"]
    for observer in ("p1", "p3"):
        sees_only_who(s, observer, "Bob")  # nobody sees whether, or what, Bob chooses to sacrifice (the answer is private until it is carried out)
    reload_mid_decision(s)
    play_through(s, "main2", {"p2": bob, "p3": carol})
    assert sum(not on_battlefield(s, c) for c in bears) == bob and sum(not on_battlefield(s, c) for c in elves) == carol
    paid = bob or carol
    assert s.state.players["p1"].life == life + (3 if paid else 0)
    assert len(s.state.zones["p1:hand"]) == hand + (1 if paid else 0)
    assert s.state.cards[troll.id].tapped == paid
    check(s)


def test_brain_gorgers_cast_trigger_is_answered_in_turn_order_and_counters_the_spell_itself(cards):
    """"When you cast this spell, any player may sacrifice a creature of their choice. If a player does, counter Brain Gorgers.": the trigger is above the
    spell on the stack (603.3, 601.2i), so it is asked first; Alice (the active player) declines, Bob sacrifices; the spell is countered (the 2007 ruling:
    the remaining players are still asked, it is not an extra payment)."""
    s = pod(cards, ["Brain Gorgers", "Grizzly Bears"], [(1, "Grizzly Bears")], [(1, "Llanowar Elves")])
    mine, bobs, carols = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p3")
    mana(s, B=1, C=3)
    gorgers = cast_from_hand(s, "Brain Gorgers")
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and d.prompt.endswith("?"):
            asked.append(d.player)
            choose(s, [next(o.id for o in d.options if o.label.startswith("Pay" if d.player == "p2" else "Don't"))])
        else:
            choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
    assert asked == ["p1", "p2", "p3"]  # APNAP: the active player first, then turn order (101.4)
    assert s.state.cards[gorgers.id].zone == "p1:graveyard"  # countered
    assert [on_battlefield(s, c) for c in (mine, bobs, carols)] == [True, False, True]
    check(s)


def test_brain_gorgers_nobody_pays_the_spell_resolves(cards):
    s = pod(cards, ["Brain Gorgers", "Grizzly Bears"], [(1, "Grizzly Bears")])
    put(s, "Grizzly Bears", "p2")
    mana(s, B=1, C=3)
    gorgers = cast_from_hand(s, "Brain Gorgers")
    play_through(s, "main1", {})
    assert s.state.cards[gorgers.id].zone == "p1:battlefield"
    check(s)


# == Michiko Konda, Truth Seeker: "that player" is the opponent whose source dealt the damage ==
def test_michiko_the_opponent_whose_source_dealt_damage_sacrifices_a_permanent_of_their_choice(cards):
    s = pod(cards, ["Michiko Konda, Truth Seeker"], ["Lightning Bolt", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    put(s, "Michiko Konda, Truth Seeker")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    carols = put(s, "Grizzly Bears", "p3")
    forest = put(s, "Forest", "p2")
    to_turn_of(s, "p2")
    life = s.state.players["p1"].life
    mana(s, "p2", R=1)
    cast_from_hand(s, "Lightning Bolt", "p2", targets=["p1"])
    settle_until_asked(s)
    assert s.state.players["p1"].life == life - 3
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (1, 1)  # Bob chooses (701.21a), not Alice
    assert {o.id for o in d.options} == {bears.id, elves.id, forest.id}  # among what Bob controls: not Carol's, not Alice's
    for observer in ("p1", "p3"):
        sees_only_who(s, observer, "Bob")
    again = reload_mid_decision(s)
    choose(again, [forest.id])
    settle(again)
    assert not on_battlefield(again, forest) and on_battlefield(again, carols)
    choose(s, [forest.id])
    settle(s)
    assert not on_battlefield(s, forest) and on_battlefield(s, bears) and on_battlefield(s, elves) and on_battlefield(s, carols)
    check(s)


# == Witch-king of Angmar: only a creature that dealt combat damage to Alice this turn, each opponent's choice among those ==
def test_witch_king_of_angmar_each_opponent_sacrifices_one_of_the_creatures_that_hit_alice(cards):
    s = pod(cards, ["Witch-king of Angmar"], [(3, "Grizzly Bears")], [(2, "Llanowar Elves")], [(1, "Young Wolf")])
    put(s, "Witch-king of Angmar")
    bobs = [put(s, "Grizzly Bears", "p2", i) for i in range(3)]  # two of them attack Alice, one stays home
    carols = [put(s, "Llanowar Elves", "p3", i) for i in range(2)]  # nothing of Carol's attacks (she can't, on Bob's turn)
    to_turn_of(s, "p2")
    ready(s, "Grizzly Bears", pid="p2")
    for c in bobs:
        s.state.rules.controlled_since[c.id].turn = 0
    attack_as(s, "p2", bobs[:2], "p1")
    block(s, "p1")
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p2"
    assert {o.id for o in d.options} == {bobs[0].id, bobs[1].id}  # the two that dealt combat damage to Alice, not the third
    sees_only_who(s, "p3", "Bob")
    reload_mid_decision(s)
    choose(s, [bobs[1].id])
    settle(s)
    assert [on_battlefield(s, c) for c in bobs] == [True, False, True]
    assert all(on_battlefield(s, c) for c in carols)  # Carol's creatures did nothing to Alice
    check(s)


# == Rakdos, Patron of Chaos: "target opponent may sacrifice two nonland, nontoken permanents of their choice. If they don't, you draw two cards." ==
@pytest.mark.parametrize(("setup", "pays", "sacrificed", "drawn"), [("two", True, 2, 0), ("two", False, 0, 2), ("one", True, 0, 2)])
def test_rakdos_patron_of_chaos_the_target_opponent_pays_with_two_permanents_or_alice_draws(cards, setup, pays, sacrificed, drawn):
    """118.12a: the target opponent decides at resolution; only a payment that can be made in full is offered (118.3), and a land or a token is no
    nonland, nontoken permanent. With only one such permanent Bob can't pay: Alice draws."""
    s = pod(cards, ["Rakdos, Patron of Chaos"], [(2, "Grizzly Bears"), "Llanowar Elves"], ["Grizzly Bears"])
    put(s, "Rakdos, Patron of Chaos")
    bobs = [put(s, "Grizzly Bears", "p2", 0), put(s, "Llanowar Elves", "p2")] if setup == "two" else [put(s, "Grizzly Bears", "p2", 0)]
    act(s, "p2", type="create_token", player="p2", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "text": ""})
    carols = put(s, "Grizzly Bears", "p3")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "main2", "end"])
    seen = []
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == "end" and not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and d.prompt.endswith("?"):
            seen.append((d.player, [o.label for o in d.options]))
            sees_only_who(s, "p3" if d.player != "p3" else "p1", "Bob")
            choose(s, [next(o.id for o in d.options if o.label.startswith("Pay" if pays else "Don't"))])
        elif d.kind == "choose_one":  # the target: Bob
            choose(s, labels=["Bob"])
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            assert d.player == "p2" and (d.min_choices, d.max_choices) == (2, 2)
            assert {o.id for o in d.options} == {c.id for c in bobs}  # not the Forests, not the Goblin token
            choose(s, [o.id for o in d.options])
    assert sum(not on_battlefield(s, c) for c in bobs) == sacrificed
    assert len(s.state.zones["p1:hand"]) == hand + drawn
    assert on_battlefield(s, carols)
    assert bool(seen) == (setup == "two")  # (the question is asked only when the payment can be made)
    check(s)


# == pumps: two groups in one sentence, a keyword read from the objects, conditional grants, "they" of a two-name card ==
def chars_of(s, name, pid="p1"):
    from app.rules.plan import Plan

    c = s.state.cards[card_named(s, name, pid).id]
    return Plan(s.state, "p1", s.cards, None).ch(c)


def attack_and_settle(s, attackers, target="p2"):
    """Alice's attack with creatures that have been under her control since the turn began; every trigger of the declaration resolved."""
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    attack_as(s, "p1", attackers, target)
    settle(s)


def test_agrus_kos_pumps_red_attackers_and_white_attackers_by_their_own_amounts(cards):
    """"attacking red creatures get +2/+0 and attacking white creatures get +0/+2": two groups, two modifiers, fixed as it resolves (611.2c); Agrus Kos
    is both colors, so he gets both; a creature of neither color (the Bears) and a red creature that doesn't attack get nothing."""
    s = pod(cards, ["Agrus Kos, Wojek Veteran", "Mardu Scout", "Soul Warden", "Grizzly Bears"], [])
    agrus, scout, warden, bears = (put(s, n) for n in ("Agrus Kos, Wojek Veteran", "Mardu Scout", "Soul Warden", "Grizzly Bears"))
    ready(s, "Agrus Kos, Wojek Veteran", "Mardu Scout", "Soul Warden", "Grizzly Bears")
    base = {n: pt(s, n) for n in ("Agrus Kos, Wojek Veteran", "Mardu Scout", "Soul Warden", "Grizzly Bears")}
    attack_and_settle(s, [agrus, scout, warden])
    assert pt(s, "Agrus Kos, Wojek Veteran") == (base["Agrus Kos, Wojek Veteran"][0] + 2, base["Agrus Kos, Wojek Veteran"][1] + 2)
    assert pt(s, "Mardu Scout") == (base["Mardu Scout"][0] + 2, base["Mardu Scout"][1])
    assert pt(s, "Soul Warden") == (base["Soul Warden"][0], base["Soul Warden"][1] + 2)
    assert pt(s, "Grizzly Bears") == base["Grizzly Bears"]
    check(s)


def test_telim_tor_gives_attacking_creatures_with_flanking_plus_one(cards):
    """"all attacking creatures with flanking get +1/+1": the keyword is read from each attacker (Telim'Tor has flanking, the Bears don't)."""
    s = pod(cards, ["Telim'Tor", "Grizzly Bears"], [])
    telim, bears = put(s, "Telim'Tor"), put(s, "Grizzly Bears")
    ready(s, "Telim'Tor", "Grizzly Bears")
    base_telim, base_bears = pt(s, "Telim'Tor"), pt(s, "Grizzly Bears")
    attack_and_settle(s, [telim, bears])
    assert pt(s, "Telim'Tor") == (base_telim[0] + 1, base_telim[1] + 1) and pt(s, "Grizzly Bears") == base_bears
    check(s)


@pytest.mark.parametrize(("name", "keyword"), [("Mardu Scout", "trample"), ("Soul Warden", "vigilance"), ("Grizzly Bears", None)])
def test_aurelia_grants_trample_to_a_red_target_and_vigilance_to_a_white_one(cards, name, keyword):
    """"that creature gets +2/+0, gains trample if it's red, and gains vigilance if it's white": each grant is judged for the target's colors (608.2c)."""
    s = pod(cards, ["Aurelia, Exemplar of Justice", name], [])
    put(s, "Aurelia, Exemplar of Justice")
    target = put(s, name)
    base = pt(s, name)
    chars_before = chars_of(s, name).keywords
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "begin_combat", "main2"])
    chosen = False
    for _ in range(40):  # to her beginning of combat: the target is chosen as the ability goes on the stack
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == "choose_cards" and target.id in {o.id for o in d.options}  # "up to one target creature you control"
            choose(s, [target.id])
            chosen = True
        elif chosen and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert chosen and s.state.turn.phase == "begin_combat"
    assert pt(s, name) == (base[0] + 2, base[1])
    gained = chars_of(s, name).keywords - chars_before
    assert gained == ({keyword} if keyword else set())
    check(s)


def test_moon_girl_and_devil_dinosaur_second_card_drawn_makes_it_6_6_with_trample(cards):
    """"…, until end of turn, Moon Girl and Devil Dinosaur's base power and toughness become 6/6 and they gain trample": "they" is the one card whose
    name is two names. In a two-player game the first player skips the first draw step (103.8a), so two Opts give the first and the second card."""
    s = pod(cards, ["Moon Girl and Devil Dinosaur", "Opt", "Opt"], [])
    put(s, "Moon Girl and Devil Dinosaur")
    name = "Moon Girl and Devil Dinosaur"
    assert pt(s, name) == (2, 2) and "trample" not in chars_of(s, name).keywords
    mana(s, U=1)
    cast_from_hand(s, "Opt")
    settle(s)
    assert pt(s, name) == (2, 2)  # the first card of the turn is not enough
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt", "p1", 1).id)
    settle(s)
    assert pt(s, name) == (6, 6) and "trample" in chars_of(s, name).keywords
    check(s)


# == Witch-king, Bringer of Ruin: "a creature with the least power among creatures they control" ==
def test_witch_king_bringer_of_ruin_the_defending_player_chooses_among_their_least_powerful_creatures(cards):
    """Bob controls a 2/2 and two 1/1s: the least power is 1, so he chooses between the two (the 2022 ruling: ties are his choice). Carol, not being
    attacked, loses nothing."""
    s = pod(cards, ["Witch-king, Bringer of Ruin"], ["Grizzly Bears", "Llanowar Elves", "Perilous Myr"], ["Grizzly Bears"])
    wk = put(s, "Witch-king, Bringer of Ruin")
    bears, elves, myr = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Perilous Myr", "p2")
    carols = put(s, "Grizzly Bears", "p3")
    ready(s, "Witch-king, Bringer of Ruin")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    attack_as(s, "p1", [wk], "p2")
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p2" and d.kind == "choose_cards" and (d.min_choices, d.max_choices) == (1, 1)
    assert {o.id for o in d.options} == {elves.id, myr.id}  # power 1 (the Myr is a 1/1 too); not the Bears
    sees_only_who(s, "p3", "Bob")
    reload_mid_decision(s)
    choose(s, [elves.id])
    settle_combat(s)
    assert [on_battlefield(s, c) for c in (bears, elves, myr, carols)] == [True, False, True, True]
    check(s)


# == Rakdos the Defiler: half of what a player controls, rounded up, chosen by that player ==
def test_rakdos_the_defiler_you_sacrifice_half_of_your_non_demons_then_the_player_he_hits_does(cards):
    """Five non-Demon permanents (3 Bears, 2 Forests): half rounded up is 3, Alice's choice; Rakdos (a Demon) isn't counted. Unblocked, he hits Bob, who
    controls four (2 Bears, 2 Forests) and sacrifices two of his own choice; Carol is untouched."""
    s = pod(cards, ["Rakdos the Defiler", (3, "Grizzly Bears")], [(2, "Grizzly Bears")], [(1, "Grizzly Bears")])
    rakdos = put(s, "Rakdos the Defiler")
    mine = [*(put(s, "Grizzly Bears", "p1", i) for i in range(3)), *(put(s, "Forest", "p1", i) for i in range(2))]
    bobs = [*(put(s, "Grizzly Bears", "p2", i) for i in range(2)), *(put(s, "Forest", "p2", i) for i in range(2))]
    carols = put(s, "Grizzly Bears", "p3")
    ready(s, "Rakdos the Defiler")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "main2"])
    attack_as(s, "p1", [rakdos], "p2")
    settle_until_asked(s)
    d = s.state.rules.decision
    assert d.player == "p1" and (d.min_choices, d.max_choices) == (3, 3) and {o.id for o in d.options} == {c.id for c in mine}
    sees_only_who(s, "p2", "Alice")
    choose(s, [mine[0].id, mine[1].id, mine[3].id])
    for _ in range(40):  # no blocks; combat damage; Bob's trigger
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and (d.min_choices, d.max_choices) == (2, 2) and {o.id for o in d.options} == {c.id for c in bobs}
    sees_only_who(s, "p3", "Bob")
    choose(s, [bobs[0].id, bobs[2].id])
    settle(s)
    assert [on_battlefield(s, c) for c in mine] == [False, False, True, False, True]
    assert [on_battlefield(s, c) for c in bobs] == [False, True, False, True]
    assert on_battlefield(s, carols) and on_battlefield(s, rakdos)
    check(s)


# == Vile Mutilator: two rounds, each opponent choosing in turn order, then the next kind ==
def test_vile_mutilator_each_opponent_sacrifices_an_enchantment_and_then_a_creature(cards):
    """The 2024 ruling: the next opponent in turn order chooses a nontoken enchantment, then each other opponent does; all are sacrificed together;
    "finally, repeat this process for nontoken creatures". Courser of Kruphix is both: Bob loses it in the first round, so his creature in the second is
    the Bears; Carol, with a token and a Bears, sacrifices the Bears (a token isn't a nontoken creature) — she has one choice only."""
    s = pod(cards, ["Vile Mutilator", "Grizzly Bears"], ["Courser of Kruphix", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    fodder = put(s, "Grizzly Bears")
    courser, bears, elves = put(s, "Courser of Kruphix", "p2"), put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    carols = put(s, "Grizzly Bears", "p3")
    act(s, "p3", type="create_token", player="p3", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "text": ""})
    mana(s, B=2, C=5)
    cast_from_hand(s, "Vile Mutilator")
    seen = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards" and d.player in ("p2", "p3"):
            seen.append((d.player, sorted(o.label for o in d.options)))
            choose(s, [d.options[0].id])
        else:  # the additional cost: a creature of Alice's (the Bears)
            choose(s, [fodder.id] if any(o.id == fodder.id for o in d.options) else [o.id for o in d.options][: max(1, d.min_choices)])
    # round one (nontoken enchantments): Bob has only the Courser, Carol none — nothing to choose; round two (nontoken creatures): Bob chooses between the Bears
    # and the Elves (the Courser is gone), Carol has one nontoken creature (the Goblin token is no nontoken creature) — nothing to choose
    assert seen == [("p2", ["Grizzly Bears", "Llanowar Elves"])]
    assert not on_battlefield(s, courser) and not on_battlefield(s, carols) and not on_battlefield(s, fodder)  # (Alice's Bears paid the additional cost)
    assert on_battlefield(s, bears) != on_battlefield(s, elves)
    assert any(c.name == "Goblin" and c.zone == "p3:battlefield" for c in s.state.cards.values())
    check(s)


# == Fungal Shambler: "you draw a card and that opponent discards a card" ==
def test_fungal_shambler_alice_draws_and_the_opponent_it_hit_discards_by_their_own_private_choice(cards):
    s = pod(cards, ["Fungal Shambler"], ["Opt", "Murder"], ["Swords to Plowshares"])
    shambler = put(s, "Fungal Shambler")
    for n in ("Opt", "Murder"):
        to_hand(s, n, "p2")
    carols = to_hand(s, "Swords to Plowshares", "p3")
    ready(s, "Fungal Shambler")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "main2"])
    attack_as(s, "p1", [shambler], "p2")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and sorted(o.label for o in d.options) == ["Murder", "Opt"] and (d.min_choices, d.max_choices) == (1, 1)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Alice drew (the first instruction), Bob chooses (the second)
    for observer in ("p1", "p3"):
        sees_only_who(s, observer, "Bob")
        assert "Murder" not in json.dumps(s.view(observer)["rules"]["decision"])
    reload_mid_decision(s)
    choose(s, labels=["Murder"])
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p2:graveyard"] == ["Murder"] and s.state.cards[carols.id].zone == "p3:hand"
    check(s)


# == a payer who is the ability's target: "draw a card unless target opponent sacrifices a creature of their choice or pays 3 life" ==
@pytest.mark.parametrize("answer", ["sacrifice", "pay", "neither"])
def test_indulgent_tormentor_the_target_opponent_may_sacrifice_or_pay_or_alice_draws(cards, answer):
    s = pod(cards, ["Indulgent Tormentor"], ["Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Indulgent Tormentor")
    bears = put(s, "Grizzly Bears", "p2")
    carols = put(s, "Grizzly Bears", "p3")
    life, hand = s.state.players["p2"].life, len(s.state.zones["p1:hand"])
    to_turn_of(s, "p1")  # (her next upkeep)
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.number >= 4 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and d.prompt.endswith("choose a target"):
            choose(s, labels=["Bob"])
        elif d.kind == "choose_one" and d.prompt.endswith("?"):
            sees_only_who(s, "p3", "Bob")
            want = {"sacrifice": "Pay Sacrifice", "pay": "Pay Pay", "neither": "Don't"}[answer]
            choose(s, [next(o.id for o in d.options if o.label.startswith(want))])
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            choose(s, [o.id for o in d.options][: max(1, d.min_choices)])
    assert (not on_battlefield(s, bears)) == (answer == "sacrifice") and on_battlefield(s, carols)
    assert s.state.players["p2"].life == life - (3 if answer == "pay" else 0)
    assert len(s.state.zones["p1:hand"]) == hand + 1 + (answer == "neither")  # her draw step's card, and the upkeep's only if Bob did neither (118.12a)
    check(s)


# == what stays manual (pinned) ==
@pytest.mark.parametrize("text", [
    # "that player" after a source YOU control dealt damage: the damaged player or the source's controller? (not read)
    "Whenever a source you control deals damage to an opponent, that player sacrifices a permanent of their choice.",
    # a lead that is about "they" and a payer who is the target: the same player twice, one of them unbound (Braids's Frightful Return)
    "At the beginning of your upkeep, target opponent may sacrifice a creature. If they don't, they lose 2 life.",
    # "Round down each time" lists (Pox Plague) are not "half the … they control, rounded down"
    "Each player sacrifices half the permanents they control of their choice, round down each time.",
    # the count of a blocked creature that isn't the source or the event's creature
    "Whenever a creature you control attacks, it gets +1/+1 until end of turn for each creature blocking it.",
    # (Odric, Lunarch Marshal is read since wave 50J: the variants are granted as the lines they are, app/rules/keyword_soup.py, tests/test_rules_wave50j_small.py)
])
def test_unread_wordings_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Card", "Creature — Test", text)
    assert coverage.of_characteristics(chs).level != "FULL"


def test_a_static_grant_of_flanking_to_creatures_with_flanking_stays_manual():
    """Cavalry Master: another instance of flanking for each — triggers.flanking counts printed instances only, so the grant would do nothing."""
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Cavalry Master", "Creature — Human Knight", "Flanking\nOther creatures you control with flanking have flanking.")
    assert coverage.of_characteristics(chs).level != "FULL"


# == Rhystic Circle: "Any player may pay {1}. If no one does, …" ==
@pytest.mark.parametrize("bob_pays", [False, True])
def test_rhystic_circle_if_no_one_pays_alice_chooses_a_source_to_prevent_damage_from(cards, bob_pays):
    """Alice paid {1} to activate and has nothing left, so Bob (with an untapped Forest) is the only one who can pay. If he does, nothing happens; if no one
    does, the shield is Alice's (609.7a): she chooses the source."""
    s = pod(cards, ["Rhystic Circle"], ["Lightning Bolt"], [])
    circle = put(s, "Rhystic Circle")
    put(s, "Forest", "p2")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=circle.id, ability=0)
    d = s.state.rules.decision
    assert d.player == "p2" and d.prompt.endswith("pay {1}?") and [o.label for o in d.options] == ["Pay {1}", "Don't pay"]
    sees_only_who(s, "p1", "Bob")
    reload_mid_decision(s)
    choose(s, labels=["Pay {1}" if bob_pays else "Don't pay"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            assert not bob_pays and d.player == "p1" and "Choose a source" in d.prompt  # only when no one paid
            choose(s, [o.id for o in d.options if o.label == "Rhystic Circle"])
    assert s.state.rules.decision is None
    check(s)
