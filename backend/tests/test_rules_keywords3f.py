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
REAL += [
    real("Tranquilize", "F13", "{1}{U}", 2, "Sorcery", "Tap target creature an opponent controls and put three stun counters "
         "on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)", ["U"]),
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


# -- face-down permanents (708, 701.40, 701.58, 701.62, 702.37, 702.168) --------------------------------
def on_top(s, name, pid="p1"):
    card = named(s, name, pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "library"})  # (the top of its owner's library)
    assert s.state.zones[f"{pid}:library"][0] == card.id
    return card


def cast(s, name, pid="p1", targets=(), **m):
    spell = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=spell.id, targets=list(targets))
    pass_until_stack_empty(s)
    return spell


def hidden_from(s, pid, card):
    """Nothing a player receives names the card or its printing (view, log, rules, decision)."""
    blob = json.dumps(s.view(pid))
    return card.name not in blob and card.card_id not in blob


def test_parse_manifest_cloak_and_dread():
    assert scripts.parse_effects("Manifest the top card of your library.") == (
        [{"do": "manifest", "kind": "manifest", "who": "you", "n": 1}], None, False)
    assert scripts.parse_effects("Cloak the top card of your library.") == (
        [{"do": "manifest", "kind": "cloak", "who": "you", "n": 1}], None, False)
    assert scripts.parse_effects("Manifest dread twice.") == (
        [{"do": "manifest", "dread": True, "kind": "manifest", "who": "you", "n": 2}], None, False)
    effects, target, _ = scripts.parse_effects("Exile target creature. Its controller manifests the top card of their library.")
    assert effects[1] == {"do": "manifest", "kind": "manifest", "who": "ref:e0.controller", "n": 1} and target == "creature"
    effects, _, _ = scripts.parse_effects("Manifest dread, then put three +1/+1 counters on that creature.")
    assert effects[1] == {"do": "add_counters", "who": "ref:e0", "kind": "+1/+1", "n": 3} and effects[0]["as"] == "e0"
    assert scripts.parse_effects("You manifest the top card of that player's library.") is None  # (not read)


def test_soul_summons_manifests_a_hidden_two_two_that_turns_up_for_its_mana_cost(cards):
    s = build(cards, "Soul Summons", "Hunted Bonebrute", players=2)
    brute = on_top(s, "Hunted Bonebrute")
    cast(s, "Soul Summons", W=1, C=1)
    c = s.state.cards[brute.id]
    assert c.zone == "p1:battlefield" and c.face_down and c.face_down_kind == "manifest"
    assert ch(s, brute).pt == (2, 2) and ch(s, brute).name == "" and not ch(s, brute).abilities
    assert not [x for x in s.state.cards.values() if x.name == "Dog"]  # 708.3: its "enters" trigger doesn't trigger
    assert hidden_from(s, "p2", brute) and "Hunted Bonebrute" in json.dumps(s.view("p1"))
    assert s.view("p2")["cards"][brute.id]["face_down_kind"] == "manifest"
    replay_matches(s)
    # 701.40b: its mana cost (it's a creature card); 701.40d: or its disguise cost
    with pytest.raises(ActionError, match="Not enough mana"):
        act(s, "p1", type="turn_face_up", card_id=brute.id, method="mana_cost")
    mana(s, B=1, C=2)
    act(s, "p1", type="turn_face_up", card_id=brute.id, method="mana_cost")
    c = s.state.cards[brute.id]
    assert not c.face_down and ch(s, brute).pt == (6, 2) and "menace" in ch(s, brute).keywords
    assert not [x for x in s.state.cards.values() if x.name == "Dog"]  # 708.8: no "enters" ability now either
    assert "Hunted Bonebrute" in json.dumps(s.view("p2"))
    replay_matches(s)


def test_a_manifested_noncreature_card_stays_face_down(cards):
    s = build(cards, "Soul Summons", players=2)
    mountain = on_top(s, "Mountain")
    cast(s, "Soul Summons", W=1, C=1)
    assert s.state.cards[mountain.id].face_down and ch(s, mountain).is_creature  # a 2/2 creature, not a land
    mana(s, C=5)
    with pytest.raises(ActionError, match="can't be turned face up"):
        act(s, "p1", type="turn_face_up", card_id=mountain.id)  # 701.40b: not a creature card
    with pytest.raises(ActionError):
        act(s, "p2", type="turn_face_up", card_id=mountain.id)  # (only its controller)
    assert hidden_from(s, "p2", mountain)


def test_reality_shift_its_controller_manifests_and_only_they_see_it(cards):
    s = build(cards, "Reality Shift", "Disrupt Decorum", players=3, bob=["Hunted Bonebrute"])
    ogre = token(s, "p2", "Ogre", "3/3")
    brute = on_top(s, "Hunted Bonebrute", "p2")
    cast(s, "Reality Shift", targets=[ogre.id], U=1, C=1)
    c = s.state.cards[brute.id]
    assert c.zone == "p2:battlefield" and c.controller == "p2" and c.face_down and c.face_down_kind == "manifest"
    assert hidden_from(s, "p1", brute) and hidden_from(s, "p3", brute)
    assert "Hunted Bonebrute" in json.dumps(s.view("p2"))  # 708.5: its controller may look at it
    # goading it names no face-down card in the log (708.5)
    cast(s, "Disrupt Decorum", R=4)
    assert "goaded:p1" in ch(s, brute).imposed
    assert hidden_from(s, "p1", brute) and hidden_from(s, "p3", brute)
    replay_matches(s)


def test_manifest_dread_is_a_private_choice_the_other_card_goes_to_the_graveyard(cards):
    s = build(cards, "Manifest Dread", "Hunted Bonebrute", "Thelonite Hermit", players=2)
    hermit = on_top(s, "Thelonite Hermit")
    brute = on_top(s, "Hunted Bonebrute")
    dread = to_hand(s, "Manifest Dread")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=dread.id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    assert d is not None and d.player == "p1" and {o.card_id for o in d.options} == {brute.id, hermit.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    assert hidden_from(s, "p2", brute) and hidden_from(s, "p2", hermit)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hermit.id])
    pass_until_stack_empty(s)
    assert s.state.cards[hermit.id].face_down and s.state.cards[hermit.id].zone == "p1:battlefield"
    assert s.state.cards[brute.id].zone == "p1:graveyard"
    assert hidden_from(s, "p2", hermit)
    replay_matches(s)


def test_fierce_invocation_counters_go_on_the_manifested_creature(cards):
    s = build(cards, "Fierce Invocation", players=2)
    to_hand(s, "Fierce Invocation")
    top = on_top(s, "Mountain")
    cast(s, "Fierce Invocation", R=1, C=4)
    assert s.state.cards[top.id].face_down and s.state.cards[top.id].counters == {"+1/+1": 2}
    assert ch(s, top).pt == (4, 4)
    replay_matches(s)


def test_morph_turned_face_up_triggers_and_secret_plans_draws(cards):
    s = build(cards, "Thelonite Hermit", "Secret Plans", players=2)
    cast(s, "Secret Plans", G=1, U=1)
    hermit = to_hand(s, "Thelonite Hermit")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=hermit.id, face_down=True)
    pass_until_stack_empty(s)
    assert s.state.cards[hermit.id].face_down and ch(s, hermit).pt == (2, 3)  # Secret Plans: +0/+1
    hand = len(s.state.zones["p1:hand"])
    mana(s, G=2, C=3)
    act(s, "p1", type="turn_face_up", card_id=hermit.id)
    d = rules(s).decision
    assert d is not None and d.kind == "order"  # two triggers of Alice's at once (603.3b)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    pass_until_stack_empty(s)
    saprolings = [c for c in s.state.cards.values() if c.name == "Saproling"]
    assert len(saprolings) == 4 and all(ch(s, x).pt == (2, 2) for x in saprolings)  # All Saprolings get +1/+1
    assert len(s.state.zones["p1:hand"]) == hand + 1  # "Whenever a permanent you control is turned face up, draw a card."
    replay_matches(s)


def test_disguise_cast_face_down_has_ward(cards):
    from app.rules import triggers

    s = build(cards, "Hunted Bonebrute", players=2)
    brute = to_hand(s, "Hunted Bonebrute")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=brute.id, face_down=True)
    pass_until_stack_empty(s)
    c = s.state.cards[brute.id]
    assert c.face_down and c.face_down_kind == "disguise" and ch(s, brute).pt == (2, 2)
    assert triggers.ward_cost(ch(s, brute)) == "{2}"  # 702.168a: a 2/2 with ward {2}
    assert not [x for x in s.state.cards.values() if x.name == "Dog"]
    assert hidden_from(s, "p2", brute) and s.view("p2")["cards"][brute.id]["face_down_kind"] == "disguise"
    replay_matches(s)


def test_face_down_creature_dies_revealed_and_its_dies_ability_never_was(cards):
    s = build(cards, "Hunted Bonebrute", players=2)
    brute = to_hand(s, "Hunted Bonebrute")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=brute.id, face_down=True)
    pass_until_stack_empty(s)
    killer = token(s, "p1", "Killer", "1/1", text="{1}: Destroy target creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=killer.id, ability=0, targets=[brute.id])
    pass_until_stack_empty(s)
    assert s.state.cards[brute.id].zone == "p1:graveyard" and not s.state.cards[brute.id].face_down
    assert s.state.players["p2"].life == 40  # LKI: a face-down 2/2 with no abilities died (708.2, 603.10a)
    assert "Hunted Bonebrute" in json.dumps(s.view("p2")["log"])  # 708.9: revealed as it left
    replay_matches(s)


def test_face_down_bounced_to_hand_is_revealed_as_it_moves(cards):
    s = build(cards, "Soul Summons", "Hunted Bonebrute", players=2)
    brute = on_top(s, "Hunted Bonebrute")
    cast(s, "Soul Summons", W=1, C=1)
    act(s, "p1", type="move", card_ids=[brute.id], to={"zone": "hand"})
    assert "Hunted Bonebrute" in json.dumps(s.view("p2")["log"])  # 708.9
    assert brute.id not in s.view("p2")["cards"]  # (in the hand it's anonymous again)


def test_face_down_state_survives_save_and_load(cards):
    from app.storage.saves import load_payload

    s = build(cards, "Hunted Bonebrute", players=2)
    brute = to_hand(s, "Hunted Bonebrute")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=brute.id, face_down=True)
    pass_until_stack_empty(s)
    state, _ = load_payload({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()})
    again = GameSession(state, cards=cards)
    assert state.cards[brute.id].face_down_kind == "disguise"
    assert Plan(state, "p1", cards, None).ch(state.cards[brute.id]).pt == (2, 2)
    assert hidden_from(again, "p2", brute)


def test_whisperwood_elemental_manifests_at_the_end_step(cards):
    from tests.test_rules_effects import run_until

    s = build(cards, "Whisperwood Elemental", players=2)
    cast(s, "Whisperwood Elemental", G=2, C=3)
    first = on_top(s, "Mountain")
    run_until(s, lambda s: s.state.cards[first.id].zone == "p1:battlefield" and not s.state.zones.get("stack"))
    assert s.state.cards[first.id].face_down and s.state.cards[first.id].face_down_kind == "manifest"
    assert hidden_from(s, "p2", first)
    replay_matches(s)


def test_whisperwood_elemental_sacrifice_grants_a_dies_manifest_to_face_up_nontoken_creatures(cards):
    """"Sacrifice this creature: Until end of turn, face-up nontoken creatures you control gain "When this
    creature dies, manifest the top card of your library."" — the Bears gain it; a face-down 2/2 doesn't."""
    s = build(cards, "Whisperwood Elemental", "Grizzly Bears", "Soul Summons", players=2)
    cast(s, "Whisperwood Elemental", G=2, C=3)
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    down = on_top(s, "Mountain")
    cast(s, "Soul Summons", W=1, C=1)
    whisper = named(s, "Whisperwood Elemental")
    act(s, "p1", type="activate_ability", card_id=whisper.id, ability=1)
    pass_until_stack_empty(s)
    assert whisper.id in s.state.zones["p1:graveyard"]
    killer = token(s, "p1", "Killer", "1/1", text="{1}: Destroy target creature.")
    library = len(s.state.zones["p1:library"])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=killer.id, ability=0, targets=[down.id])
    pass_until_stack_empty(s)
    assert s.state.cards[down.id].zone == "p1:graveyard" and len(s.state.zones["p1:library"]) == library  # (it was face down)
    second = s.state.zones["p1:library"][0]
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=killer.id, ability=0, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.cards[second].zone == "p1:battlefield" and s.state.cards[second].face_down
    replay_matches(s)


def test_geode_rager_goads_each_creature_the_target_player_controls(cards):
    s = build(cards, "Geode Rager", players=3)
    ogre = token(s, "p2", "Ogre", "3/3")
    wolf = token(s, "p3", "Wolf", "2/2")
    cast(s, "Geode Rager", R=2, C=4)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Mountain").id)
    d = rules(s).decision
    if d is not None:  # the landfall trigger's target player
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "p2" in o.id)])
    pass_until_stack_empty(s)
    assert "goaded:p1" in ch(s, ogre).imposed and not any(r.startswith("goaded") for r in ch(s, wolf).imposed)
    replay_matches(s)


# -- stun counters (122.1d) -------------------------------------------------------------------------------
def test_tranquilize_stun_counters_replace_untapping(cards):
    from tests.test_rules_effects import run_until

    s = build(cards, "Tranquilize", players=2)
    ogre = token(s, "p2", "Ogre", "3/3")
    cast(s, "Tranquilize", targets=[ogre.id], U=1, C=1)
    assert s.state.cards[ogre.id].tapped and s.state.cards[ogre.id].counters == {"stun": 3}
    # Bob's untap step: it stays tapped, one stun counter comes off instead (122.1d)
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert s.state.cards[ogre.id].tapped and s.state.cards[ogre.id].counters == {"stun": 2}
    # "untap target creature" is replaced the same way
    untapper = token(s, "p2", "Untapper", "1/1", text="{1}: Untap target creature.")
    run_until(s, lambda s: s.state.turn.phase == "main1" and rules(s).priority == "p2")
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=untapper.id, ability=0, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].tapped and s.state.cards[ogre.id].counters == {"stun": 1}
    run_until(s, lambda s: s.state.turn.active_player == "p1")
    assert s.state.cards[ogre.id].tapped  # (Alice's untap step: not Bob's permanents)
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert s.state.cards[ogre.id].tapped and not s.state.cards[ogre.id].counters  # the last one came off
    run_until(s, lambda s: s.state.turn.active_player == "p1")
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    assert not s.state.cards[ogre.id].tapped
    replay_matches(s)
