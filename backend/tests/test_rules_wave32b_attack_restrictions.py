"""Wave 32B: attack restrictions aimed at the effect's controller, with durations (CR 2026-09-25), real Oracle text
(tests/fixtures/wave32b_attack_cards.json, from data/cards.sqlite). Every scenario has three players, a replay and a save and a load.

* 508.1c: a creature that can't attack a player (or a planeswalker / battle they control) can't be declared as attacking them, but it may attack anyone else.
* 611.2a-c: "until your next turn" ends as that player's next turn begins (500.4); "this turn" / "this combat" end with the turn / combat; "during their next
  turn" is the next turn of the player it names. The effects change no characteristics and no control, so they reach the creatures the player controls when
  the attack is declared, not only the ones there when the effect began.
* 508.1d, 508.1h-j: "unless their controller pays {2} for each of those creatures" is an attack cost for the length of the duration (Forbidding Spirit).
* 303.4: "Each creature that's enchanted by an Aura you control" counts the Auras of the effect's controller only (Eriette).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, until
from tests.test_rules_effects import replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave32b_attack_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w32b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


EXTRA.append(card("Test Player Hex", set_code="w32b", number="B90", mana_cost="{1}", cmc=1.0, type_line="Sorcery", colors=[], color_identity=[], keywords=[],
                  oracle_text="Creatures that player controls can't attack you this turn."))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def build3(cards, mine=(), bob=(), carol=(), seats=3):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (20, "Mountain")]),
             deck(cards, "Atraxa, Praetors' Voice", [(20, "Swamp")])][:seats]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol", "Dave")[:seats], decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def goes(s, turn, pid):
    """Pass until ``pid`` is asked to declare attackers on this turn."""
    until(s, lambda s: s.state.turn.number == turn and (d := s.state.rules.decision) is not None
          and d.kind == "declare_attackers" and d.player == pid)


def attack(s, pid, *pairs):
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def refused(s, pid, c, target):
    """The declaration is refused (508.1c): the decision stays and nothing is attacking."""
    with pytest.raises(ActionError, match=f"{c.name} can't attack {s.state.players[target].name if target in s.state.players else ''}"):
        attack(s, pid, (c, target))
    assert s.state.cards[c.id].attacking is None


def end_of_turn_effects(s):
    return [e for e in s.state.rules.effects if e.imposes]


@pytest.mark.parametrize("name", ["Chronomantic Escape", "Web of Inertia", "Champions of Minas Tirith", "The Second Doctor",
                                  "Willie Lumpkin, Postman", "Forbidding Spirit", "Eriette of the Charmed Apple", "Killian, Decisive Mentor",
                                  "Sivitri, Dragon Master"])  # (Sivitri: wave 49D, an attack cost of life)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", ["Call for Aid"])  # (Orzhov Advokist: FULL since wave 53A, player_choices.py - each player chooses a creature they control, CR 101.4)
def test_still_manual(cards, name):
    """Call for Aid ("You can't attack that player this turn", "You can't sacrifice those creatures") is not read."""
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL", name


def test_the_player_is_only_read_where_a_trigger_names_one(cards):
    """"Creatures that player controls can't attack you this turn." in a spell with no player to be "that player" is not read."""
    assert coverage.of_card_data(cards.resolve("Test Player Hex")).level == "PARTIAL"


def test_chronomantic_escape_until_your_next_turn_each_other_player_can_still_be_attacked(cards):
    """"Until your next turn, creatures can't attack you.": Bob and Carol can't attack Alice, but attack each other, a creature that changes hands is
    just as restricted, and it ends as Alice's next turn begins (500.4)."""
    s = build3(cards, mine=["Chronomantic Escape"])
    ogre = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    wolf = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    thief = token(s, "p2", "Bob Thief", "1/1", "Haste")
    to_hand(s, "Chronomantic Escape")
    mana(s, W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=named(s, "Chronomantic Escape", "p1").id)
    settle(s)
    assert named(s, "Chronomantic Escape", "p1").zone == "p1:exile"  # (its second sentence: exiled with three time counters)
    assert len(end_of_turn_effects(s)) == 1
    assert [(m.name, m.text) for m in s.state.cards[ogre.id].effects] == [("Can't attack Alice", "until your next turn")]  # (the table marker)
    check(s)
    goes(s, 2, "p2")  # Bob's turn
    refused(s, "p2", ogre, "p1")
    check(s)
    attack(s, "p2", (ogre, "p3"))  # Carol is not protected
    assert s.state.cards[ogre.id].attacking is not None
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    act(s, "p3", type="set_controller", card_ids=[thief.id], player="p3")  # Carol takes Bob's creature (haste doesn't matter: it has it)
    goes(s, 3, "p3")
    refused(s, "p3", thief, "p1")  # it is restricted under its new controller too
    refused(s, "p3", wolf, "p1")
    attack(s, "p3", (thief, "p2"), (wolf, "p2"))
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert not end_of_turn_effects(s)  # "until your next turn": gone as Alice's turn began
    assert not any(c.effects for c in s.state.cards.values())  # (and so are the table markers it wrote)
    check(s)


def answer_asks(s, **yes):
    """Answer the questions that come up ("p1": True …; anyone not named says no: "yes" / "no", "pay" / "decline"; a choice of cards takes the first)
    until the stack is empty."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is None or d.kind in ("declare_attackers", "declare_blockers"):
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        if "yes" in ids or "pay" in ids:
            pick = ("yes" if "yes" in ids else "pay") if yes.get(d.player) else ("no" if "no" in ids else "decline")
        else:
            pick = ids[0]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    raise AssertionError("never settled")


def test_the_second_doctor_each_opponent_who_draws_cant_attack_you_during_their_next_turn(cards):
    """"Each player may draw a card. Each opponent who does can't attack you or permanents you control during their next turn.": Alice and Bob draw,
    Carol doesn't. Bob can't attack Alice or her planeswalker on his turn (but can attack Carol); Carol can; it was Bob's one turn."""
    s = build3(cards, mine=["The Second Doctor", "Gideon Jura"])
    put(s, "The Second Doctor")
    gideon = put(s, "Gideon Jura")
    bob = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    carol = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    thief = token(s, "p3", "Carol Thief", "1/1", "Haste")
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "confirm")
    answer_asks(s, p1=True, p2=True)
    said = ["".join(x.t or x.name or "?" for x in e.parts) for e in s.state.log]
    turn_one = said[said.index("— End step —"):said.index("Turn 2: Bob")]
    assert [x for x in turn_one if "drew a card" in x] == ["Alice drew a card", "Bob drew a card"]  # (Carol said no)
    check(s)  # (Bob's restriction waits for his turn)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    act(s, "p2", type="set_controller", card_ids=[thief.id], player="p2")  # Bob takes a creature after the restriction began: it is his, so it is restricted
    goes(s, 2, "p2")
    assert [(e.duration, e.until_player) for e in end_of_turn_effects(s)] == [("end_of_next_turn", "p2")]
    refused(s, "p2", bob, "p1")
    refused(s, "p2", thief, "p1")
    refused(s, "p2", bob, gideon.id)  # "permanents you control": her planeswalker too
    check(s)
    attack(s, "p2", (bob, "p3"))
    assert s.state.cards[bob.id].attacking is not None
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert not end_of_turn_effects(s)  # Bob's next turn is over
    goes(s, 3, "p3")
    attack(s, "p3", (carol, "p1"))  # Carol said no: nothing stops her
    assert s.state.cards[carol.id].attacking is not None
    check(s)


def asked_by(s, pid):
    """Pass until ``pid`` is asked something (not to declare attackers or blockers)."""
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.player == pid
          and d.kind not in ("declare_attackers", "declare_blockers"))
    return s.state.rules.decision


def test_web_of_inertia_the_player_who_declines_cant_attack_you_this_turn(cards):
    """"At the beginning of combat on each opponent's turn, that player may exile a card from their graveyard. If the player doesn't, creatures they control
    can't attack you this turn.": Bob declines (his creatures can't attack Alice, but attack Carol); Carol exiles a card on her turn and attacks Alice."""
    s = build3(cards, mine=["Web of Inertia"])
    put(s, "Web of Inertia")
    bob = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    wolf = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    for pid in ("p2", "p3"):  # (a card in each graveyard to exile)
        act(s, pid, type="move", card_ids=[s.state.zones[f"{pid}:library"][0]], to={"player": pid, "zone": "graveyard"})
    d = asked_by(s, "p2")
    assert s.state.turn.number == 2 and s.state.turn.phase == "begin_combat" and [o.id for o in d.options] == ["pay", "decline"]
    check(s)  # (a save with Bob's answer pending)
    answer_asks(s)  # Bob says no
    assert [(e.duration, e.who is not None) for e in end_of_turn_effects(s)] == [("end_of_turn", True)]
    goes(s, 2, "p2")
    refused(s, "p2", bob, "p1")
    check(s)
    attack(s, "p2", (bob, "p3"))
    assert s.state.cards[bob.id].attacking is not None
    asked_by(s, "p3")
    assert s.state.turn.number == 3 and not end_of_turn_effects(s)  # "this turn": it was Bob's turn
    graveyard = len(s.state.zones["p3:graveyard"])
    answer_asks(s, p3=True)  # Carol exiles a card: no restriction
    assert len(s.state.zones["p3:graveyard"]) == graveyard - 1 and not end_of_turn_effects(s)
    goes(s, 3, "p3")
    attack(s, "p3", (wolf, "p1"))
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main2" and s.state.rules.decision is None)
    assert s.state.players["p1"].life == 38  # (nothing blocked: the 2/2 hit Alice)
    check(s)


def test_champions_of_minas_tirith_pay_or_cant_attack_the_monarch_this_combat(cards):
    """"At the beginning of combat on each opponent's turn, if you're the monarch, that opponent may pay {X}, where X is the number of cards in their hand. If
    they don't, they can't attack you this combat.": Bob has two cards and two lands and pays; Carol can't pay for her hand and is stopped from attacking
    Alice (not Bob) for that combat only."""
    s = build3(cards, mine=["Champions of Minas Tirith"])
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Champions of Minas Tirith").id)
    settle(s)
    assert s.state.table.monarch == "p1"
    bob = token(s, "p2", "Bob Wall", "0/4", "Haste")  # (no damage: nobody takes the monarchy)
    carol = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    for pid, held in (("p2", 1), ("p3", 3)):  # (one more is drawn on the turn: two cards for Bob, four for Carol)
        act(s, pid, type="move", card_ids=list(s.state.zones[f"{pid}:library"][:held]), to={"player": pid, "zone": "hand"})
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:2]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    d = asked_by(s, "p2")
    assert s.state.turn.number == 2 and [o.id for o in d.options] == ["pay", "decline"] and "{2}" in d.prompt
    check(s)
    answer_asks(s, p2=True)  # Bob pays {2} (his two lands)
    assert all(s.state.cards[c].tapped for c in islands) and not end_of_turn_effects(s)
    goes(s, 2, "p2")
    attack(s, "p2", (bob, "p1"))
    assert s.state.cards[bob.id].attacking.id == "p1"  # (Bob paid: he attacks the monarch)
    goes(s, 3, "p3")  # Carol has no lands: she can't pay {4}, so she isn't offered the payment (118.3) and doesn't pay
    assert [(e.duration, e.who is not None) for e in end_of_turn_effects(s)] == [("end_of_combat", True)]
    refused(s, "p3", carol, "p1")
    check(s)
    attack(s, "p3", (carol, "p2"))
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main2" and s.state.rules.decision is None)
    assert not end_of_turn_effects(s)  # "this combat": over
    check(s)


@pytest.mark.parametrize("draws", [True, False])
def test_willie_lumpkin_the_opponent_who_draws_cant_attack_you_during_their_next_turn(cards, draws):
    """"Whenever Willie Lumpkin deals combat damage to an opponent, you draw a card and that player may draw a card. If they do, that player can't attack you
    or permanents you control during their next turn.": Bob draws and then can't attack Alice on his turn (he attacks Carol); declining leaves him free."""
    s = build3(cards, mine=["Willie Lumpkin, Postman"])
    willie = put(s, "Willie Lumpkin, Postman")
    bob = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    goes(s, 4, "p1")  # (Willie has been under Alice's control since her last turn: 302.6)
    attack(s, "p1", (willie, "p2"))  # (he can't be blocked)
    d = asked_by(s, "p2")
    assert [o.id for o in d.options] == ["yes", "no"]  # Bob's own question (draw a card?)
    check(s)
    hand = len(s.state.zones["p2:hand"])
    answer_asks(s, p2=draws)
    assert len(s.state.zones["p2:hand"]) == hand + draws
    check(s)
    goes(s, 5, "p2")
    if draws:
        assert [(e.duration, e.until_player) for e in end_of_turn_effects(s)] == [("end_of_next_turn", "p2")]
        refused(s, "p2", bob, "p1")
        attack(s, "p2", (bob, "p3"))
    else:
        assert not end_of_turn_effects(s)
        attack(s, "p2", (bob, "p1"))
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main2" and s.state.rules.decision is None)
    assert (s.state.players["p3"].life, s.state.players["p1"].life) == ((37, 40) if draws else (40, 37))  # (nobody blocked: Bob hit Carol, or Alice, for 3)
    check(s)
    until(s, lambda s: s.state.turn.number == 6 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert not end_of_turn_effects(s)  # Bob's next turn is over
    check(s)


def test_forbidding_spirit_attack_cost_until_your_next_turn(cards):
    """"When this creature enters, until your next turn, creatures can't attack you or planeswalkers you control unless their controller pays {2} for each of
    those creatures.": an attack cost (508.1h-j) for Bob and Carol, free against anyone else; gone when Alice's turn begins."""
    s = build3(cards, mine=["Forbidding Spirit"])
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Forbidding Spirit").id)
    settle(s)
    bob = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    carol = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    assert [(e.duration, e.until_player) for e in end_of_turn_effects(s)] == [("next_turn", "p1")]
    check(s)
    goes(s, 2, "p2")
    with pytest.raises(ActionError, match=r"Attacking costs \{2\}"):
        attack(s, "p2", (bob, "p1"))  # no mana
    islands = [c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island"][:2]
    act(s, "p2", type="move", card_ids=islands, to={"player": "p2", "zone": "battlefield"})
    check(s)
    attack(s, "p2", (bob, "p1"))  # {2} paid by the engine with his two lands
    assert s.state.cards[bob.id].attacking.id == "p1" and all(s.state.cards[c].tapped for c in islands)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    goes(s, 3, "p3")
    with pytest.raises(ActionError, match=r"Attacking costs \{2\}"):
        attack(s, "p3", (carol, "p1"))  # she has no lands
    attack(s, "p3", (carol, "p2"))  # Bob costs nothing to attack
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main2" and s.state.rules.decision is None)
    assert s.state.players["p2"].life == 38
    check(s)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert not end_of_turn_effects(s) and not any(c.effects for c in s.state.cards.values())  # "until your next turn": gone, with its table markers
    check(s)


def test_eriette_creatures_enchanted_by_your_auras_cant_attack_you_only_theirs(cards):
    """"Each creature that's enchanted by an Aura you control can't attack you or planeswalkers you control.": Alice's Aura on Bob's creature stops it from
    attacking her or her planeswalker (and under Carol, who takes it, it attacks Bob); Carol's own Aura on her creature doesn't (the Aura isn't Alice's),
    nor does a creature with no Aura."""
    s = build3(cards, mine=["Eriette of the Charmed Apple", "Holy Strength", "Gideon Jura"], carol=["Holy Strength"])
    put(s, "Eriette of the Charmed Apple")
    gideon = put(s, "Gideon Jura")
    bob = token(s, "p2", "Bob Ogre", "3/3", "Haste")
    bare = token(s, "p2", "Bob Bare", "1/1", "Haste")
    wolf = token(s, "p3", "Carol Wolf", "2/2", "Haste")
    mine, theirs = put(s, "Holy Strength"), put(s, "Holy Strength", "p3")
    act(s, "p1", type="attach", card_ids=[mine.id], to=bob.id)
    act(s, "p3", type="attach", card_ids=[theirs.id], to=wolf.id)
    check(s)
    goes(s, 2, "p2")
    refused(s, "p2", bob, "p1")
    refused(s, "p2", bob, gideon.id)  # "or planeswalkers you control"
    check(s)
    attack(s, "p2", (bare, "p1"))  # a creature with no Aura of Alice's isn't stopped
    assert s.state.cards[bare.id].attacking.id == "p1"
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    act(s, "p3", type="set_controller", card_ids=[bob.id], player="p3")  # Carol takes the enchanted creature: still Alice's Aura
    goes(s, 3, "p3")
    refused(s, "p3", bob, "p1")
    attack(s, "p3", (wolf, "p1"), (bob, "p2"))
    assert s.state.cards[wolf.id].attacking.id == "p1" and s.state.cards[bob.id].attacking.id == "p2"
    check(s)


@pytest.mark.parametrize("enchanted", [True, False])
def test_killian_whenever_creatures_enchanted_by_an_aura_you_control_attack_draw(cards, enchanted):
    """"Whenever one or more creatures that are enchanted by an Aura you control attack, draw a card." (Killian, Decisive Mentor: the same selector as Eriette's):
    Alice's creature with her Holy Strength draws, one with none doesn't."""
    s = build3(cards, mine=["Killian, Decisive Mentor", "Holy Strength"])
    ally, plain = token(s, "p1", "Ally", "2/2", "Haste"), token(s, "p1", "Plain", "2/2", "Haste")
    aura = put(s, "Holy Strength")
    act(s, "p1", type="attach", card_ids=[aura.id], to=ally.id)
    put(s, "Killian, Decisive Mentor")  # (after the Aura: its other trigger is about enchantments that enter)
    settle(s)
    hand = len(s.state.zones["p1:hand"])
    goes(s, 1, "p1")
    attack(s, "p1", (ally if enchanted else plain, "p2"))
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + enchanted
    check(s)
