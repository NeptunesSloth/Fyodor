"""Keyword actions and face-down permanents (wave 3F): goad (701.15), manifest / manifest dread /
cloak (701.40, 701.62, 701.58), disguise and morph (702.168, 702.37), face-down rules (708) and the
hidden information around them. Real Commander cards; every scenario replays exactly."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches


def real(name, number, cost, cmc, type_line, text, colors, pt=None):
    """A real Commander card, its Oracle text transcribed from data/cards.sqlite (2026-09-30 bulk)."""
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=number, mana_cost=cost, cmc=float(cmc), type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **extra)


GOAD_REMINDER = ("(Until your next turn, that creature attacks each combat if able and attacks a player other than you if able.)")
MANIFEST_REMINDER = ("(Put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its mana cost if "
                     "it's a creature card.)")
REAL = [
    real("Disrupt Decorum", "F1", "{2}{R}{R}", 4, "Sorcery", "Goad all creatures you don't control. (Until your next turn, "
         "those creatures attack each combat if able and attack a player other than you if able.)", ["R"]),
    real("Vengeful Ancestor", "F2", "{2}{R}{R}", 4, "Creature — Spirit Dragon", "Flying\nWhenever this creature enters or "
         f"attacks, goad target creature. {GOAD_REMINDER}\nWhenever a goaded creature attacks, it deals 1 damage to its "
         "controller.", ["R"], ("3", "4")),
    real("Whisperwood Elemental", "F3", "{3}{G}{G}", 5, "Creature — Elemental", "At the beginning of your end step, manifest "
         f"the top card of your library. {MANIFEST_REMINDER}\nSacrifice this creature: Until end of turn, face-up nontoken "
         "creatures you control gain \"When this creature dies, manifest the top card of your library.\"", ["G"], ("4", "4")),
    real("Reality Shift", "F4", "{1}{U}", 2, "Instant", "Exile target creature. Its controller manifests the top card of their "
         "library. (That player puts the top card of their library onto the battlefield face down as a 2/2 creature. If it's a "
         "creature card, it can be turned face up any time for its mana cost.)", ["U"]),
    real("Soul Summons", "F5", "{1}{W}", 2, "Sorcery", f"Manifest the top card of your library. {MANIFEST_REMINDER}", ["W"]),
    real("Manifest Dread", "F6", "{1}{G}", 2, "Sorcery", "Manifest dread. (Look at the top two cards of your library. Put one "
         "onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its "
         "mana cost if it's a creature card.)", ["G"]),
    real("Hunted Bonebrute", "F7", "{2}{B}", 3, "Creature — Skeleton Beast", "Menace\nWhen this creature enters, target "
         "opponent creates two 1/1 white Dog creature tokens.\nWhen this creature dies, each opponent loses 3 life.\n"
         "Disguise {1}{B}", ["B"], ("6", "2")),
    real("Fierce Invocation", "F8", "{4}{R}", 5, "Sorcery", "Manifest the top card of your library, then put two +1/+1 counters "
         "on it. (To manifest a card, put it onto the battlefield face down as a 2/2 creature. Turn it face up any time for its "
         "mana cost if it's a creature card.)", ["R"]),
    real("Thelonite Hermit", "F9", "{3}{G}", 4, "Creature — Elf Shaman", "All Saprolings get +1/+1.\nMorph {3}{G}{G} (You may "
         "cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature "
         "is turned face up, create four 1/1 green Saproling creature tokens.", ["G"], ("1", "1")),
    real("Secret Plans", "F10", "{G}{U}", 2, "Enchantment", "Face-down creatures you control get +0/+1.\nWhenever a permanent "
         "you control is turned face up, draw a card.", ["G", "U"]),
    real("Geode Rager", "F11", "{4}{R}{R}", 6, "Creature — Elemental", "First strike\nLandfall — Whenever a land you control "
         "enters, goad each creature target player controls. (Until your next turn, those creatures attack each combat if able "
         "and attack a player other than you if able.)", ["R"], ("4", "3")),
    real("Taunting Kobold", "F12", "{R}", 1, "Creature — Kobold", "Haste\nWhenever this creature attacks, goad target creature "
         f"an opponent controls. {GOAD_REMINDER}", ["R"], ("0", "1")),
]
NAMES = [c["name"] for c in REAL]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, *names, players=3, bob=(), carol=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Mountain")])
    decks = [alice, deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")]),
             deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (10, "Mountain")])][:players]
    setups = [PlayerSetup(n, cards=d) for n, d in zip(["Alice", "Bob", "Carol"], decks, strict=False)]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid=None):
    return next(c for c in s.state.cards.values() if c.name == name and (pid is None or c.owner == pid))


def to_hand(s, name, pid="p1"):
    card = named(s, name, pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "hand"})
    return card


def token(s, pid, name, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                        "toughness": t, "text": text})
    return named(s, name, pid)


def ch(s, card):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def rules(s):
    return s.state.rules


def until_attackers(s, pid):
    """Pass (declaring no attackers for anyone else) until ``pid`` declares attackers."""
    for _ in range(80):
        d = rules(s).decision
        if d is not None and d.kind == "declare_attackers":
            if d.player == pid:
                return d
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, rules(s).priority, type="pass_priority")
    raise AssertionError("never got there")


# -- goad (701.15) ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "effects", "target"), [
    ("Goad target creature.", [{"do": "goad", "who": "target"}], 'sel:{"types":["Creature"]}'),
    ("Goad all creatures you don't control.", [{"do": "goad", "who": 'sel:{"controller":"opponent","types":["Creature"]}'}], None),
    ("Goad each creature target player controls.", [{"do": "goad", "who": "target", "controlled": True}], "player"),
    ("Goad up to two target creatures.", [{"do": "goad", "who": "target:0"}],
     [{"what": 'sel:{"types":["Creature"]}', "min": 0, "max": 2}]),
    ("Put a +1/+1 counter on target creature and goad it.",
     [{"do": "add_counters", "who": "target", "kind": "+1/+1", "n": 1}, {"do": "goad", "who": "target"}], "creature"),
])
def test_parse_goad(text, effects, target):
    assert scripts.parse_effects(text) == (effects, target, False)


def test_disrupt_decorum_goads_until_alices_next_turn(cards):
    s = build(cards, "Disrupt Decorum")
    ogre = token(s, "p2", "Ogre", "3/3")
    wolf = token(s, "p3", "Wolf", "2/2")
    mine = token(s, "p1", "Bear", "2/2")
    decorum = to_hand(s, "Disrupt Decorum")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=decorum.id)
    pass_until_stack_empty(s)
    assert ch(s, ogre).imposed >= {"goaded:p1"} and ch(s, wolf).imposed >= {"goaded:p1"}
    assert not any(r.startswith("goaded:") for r in ch(s, mine).imposed)  # "you don't control"
    assert "Goaded" in json.dumps(s.view("p3")["cards"][ogre.id])  # a public marker
    replay_matches(s)
    # (Alice's own creatures are new: her combat has no attackers to declare.) Bob's turn: the Ogre must attack, and must attack Carol (a player other than Alice)
    until_attackers(s, "p2")
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    with pytest.raises(ActionError, match="other than Alice"):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p3"}])
    assert s.state.cards[ogre.id].attacking is not None or s.state.cards[ogre.id].tapped
    # Carol's turn: the Wolf too
    until_attackers(s, "p3")
    with pytest.raises(ActionError):
        act(s, "p3", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    act(s, "p3", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p2"}])
    # Alice's next turn begins: the goad ends (701.15a), markers too
    until_attackers(s, "p1")
    assert not any(r.startswith("goaded:") for r in ch(s, ogre).imposed)
    assert "Goaded" not in json.dumps(s.view("p2")["cards"].get(ogre.id, {}))
    replay_matches(s)


def test_goaded_by_two_players_and_a_new_object(cards):
    """701.15c: goaded by Alice and Bob, Carol's creature must attack a player other than both if
    able — with three players there is none, so attacking either obeys one of the two; 701.15d:
    goading again changes nothing; a creature that changes zones is a new object (400.7)."""
    s = build(cards, players=3)
    wolf = token(s, "p3", "Wolf", "2/2")
    ctx = {"controller": "p1", "source_card": None, "source_object": None, "targets": [
        {"id": wolf.id, "object_id": rules(s).object_id(wolf.id)}]}
    from app.rules import keyword_actions as K

    plan = Plan(s.state, "p1", s.cards, None)
    for pid in ("p1", "p1", "p2"):
        K.goad(plan, {**ctx, "controller": pid}, {"do": "goad", "who": "target"})
    assert K.goaded_by(plan.ch(s.state.cards[wolf.id])) == {"p1", "p2"}
    assert sum(1 for e in plan.rules.effects if "goaded:p1" in e.imposes) == 1  # 701.15d


def test_goad_triggers_on_a_real_creature(cards):
    """Vengeful Ancestor: "Whenever this creature enters or attacks, goad target creature." """
    s = build(cards, "Vengeful Ancestor", players=2)
    ogre = token(s, "p2", "Ogre", "3/3")
    ancestor = to_hand(s, "Vengeful Ancestor")
    mana(s, R=3, C=2)
    act(s, "p1", type="cast_spell", card_id=ancestor.id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    if d is not None and d.kind != "declare_attackers":  # the trigger's target
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == ogre.id)])
    pass_until_stack_empty(s)
    assert "goaded:p1" in ch(s, ogre).imposed
    until_attackers(s, "p2")
    # two players: no player other than Alice to attack — it still must attack (701.15b, 508.1d)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    replay_matches(s)
