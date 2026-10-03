"""Token-creation wording (app/rules/token_grammar.py, CR 701.7 / 111.10 / 508.4): what each form
parses to, and the tokens on the table afterwards — type line, colors, text, tapped, counts, and
"tapped and attacking" during combat. Every scenario also checks that replaying the recorded
history reproduces the table exactly."""

from __future__ import annotations

import json

import pytest

from app.rules import scripts
from tests.game_helpers import act, find, zone
from tests.test_rules_attachments import build, ch, named, token
from tests.test_rules_combat import automate, block, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

FORESTS = 'sel:{"controller":"you","subtypes":["Forest"]}'
GOBLINS = 'sel:{"controller":"you","subtypes":["Goblin"]}'


def tok(name, p, t, colors, type_line, text="", **more):
    return {"do": "create_token", "who": "you", "n": 1, **more,
            "token": {"name": name, "power": p, "toughness": t, "colors": colors, "type_line": type_line, "text": text}}


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("Create a tapped Treasure token.",
     [{**tok("Treasure", None, None, [], "Token Artifact — Treasure", "{T}, Sacrifice this token: Add one mana of any color."),
       "tapped": True}]),
    ("Create two tapped 2/2 black Zombie creature tokens.",
     [{**tok("Zombie", "2", "2", ["B"], "Token Creature — Zombie"), "n": 2, "tapped": True}]),
    ("Create a 1/1 red Goblin Wizard creature token with prowess.",
     [tok("Goblin Wizard", "1", "1", ["R"], "Token Creature — Goblin Wizard", "Prowess")]),
    ("Create a 1/1 white Soldier creature token with flying, first strike, and lifelink.",
     [tok("Soldier", "1", "1", ["W"], "Token Creature — Soldier", "Flying\nFirst strike\nLifelink")]),
    ("Create two 2/2 colorless Wizard Soldier creature tokens named Cadet.",
     [{**tok("Cadet", "2", "2", [], "Token Creature — Wizard Soldier"), "n": 2}]),
    ('Create a 1/1 black and green Pest creature token with "When this token dies, you gain 1 life."',
     [tok("Pest", "1", "1", ["B", "G"], "Token Creature — Pest", "When this creature dies, you gain 1 life.")]),
    ('Create a 1/1 black Rat creature token with "This token can\'t block."',
     [tok("Rat", "1", "1", ["B"], "Token Creature — Rat", "This creature can't block.")]),
    ('Create a 3/6 black and red Avatar creature token with haste and "Whenever this token attacks, it deals 1 damage to each opponent."',
     [tok("Avatar", "3", "6", ["B", "R"], "Token Creature — Avatar",
          "Haste\nWhenever this creature attacks, it deals 1 damage to each opponent.")]),
    ('Create a 0/1 colorless Eldrazi Spawn creature token. It has "Sacrifice this token: Add {C}."',
     [tok("Eldrazi Spawn", "0", "1", [], "Token Creature — Eldrazi Spawn", "Sacrifice this token: Add {C}.")]),
    ("Create a 2/2 green Wolf creature token for each Forest you control.",
     [{**tok("Wolf", "2", "2", ["G"], "Token Creature — Wolf"), "n": {"count": FORESTS}}]),
    ("Create two 1/1 green Saproling creature tokens for each Forest you control.",
     [{**tok("Saproling", "1", "1", ["G"], "Token Creature — Saproling"), "n": {"times": [2, {"count": FORESTS}]}}]),
    ("Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
     [{**tok("Goblin", "1", "1", ["R"], "Token Creature — Goblin"), "n": {"count": GOBLINS}}]),
    ("Create X 1/1 white Soldier creature tokens.", [{**tok("Soldier", "1", "1", ["W"], "Token Creature — Soldier"), "n": {"x": 1}}]),
    ("Create a Lander token.",
     [tok("Lander", None, None, [], "Token Artifact — Lander",
          "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.")]),
    ("Create a 1/1 red Goblin creature token that's tapped and attacking.",
     [{**tok("Goblin", "1", "1", ["R"], "Token Creature — Goblin"), "do": "create_attacking", "tapped": True}]),
    ("Create two 1/1 red Goblin creature tokens that are tapped and attacking.",
     [{**tok("Goblin", "1", "1", ["R"], "Token Creature — Goblin"), "do": "create_attacking", "n": 2, "tapped": True}]),
    ("Create a 1/1 colorless Thopter artifact creature token with flying.",
     [tok("Thopter", "1", "1", [], "Token Artifact Creature — Thopter", "Flying")]),
])
def test_parse_token_forms(text, expected):
    assert scripts.parse_effects(text) == (expected, None, False)


@pytest.mark.parametrize("text", [
    "Create a 1/1 white Knight creature token with banding.",  # a keyword the engine doesn't implement (wave 6C: decayed now is)
    "Create a 1/1 blue Faerie creature token with flying for each spell you cast this turn.",  # (no such count)
    'Create a 1/1 white Human creature token with "{2}: Transform this token."',  # an ability the engine can't run
    "Create a 1/1 green Foo creature token.",  # not a creature type
    "Create a token that's a copy of it.",  # copies: not this grammar
    "Create an Incubator token.",  # 111.10i: a double-faced token that transforms
    "Create a Young Hero Role token attached to target creature you control.",  # (wave 6C: a Role whose ability isn't run)
    "Create a Treasure token with flying.",
])
def test_unknown_token_wordings_stay_manual(text):
    assert scripts.parse_effects(text) is None


# -- scenarios ----------------------------------------------------------------------------
def activate(s, card, pid="p1", **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":battlefield")]


def test_tapped_predefined_token(cards):
    s = build(cards)
    src = token(s, "p1", "Smuggler", text="{1}: Create a tapped Treasure token.")
    activate(s, src)
    (treasure,) = tokens(s, "Treasure")
    assert treasure.tapped and treasure.token.type_line == "Token Artifact — Treasure"
    assert treasure.token.text == "{T}, Sacrifice this token: Add one mana of any color."
    assert "Treasure" in ch(s, treasure).subtypes and "Artifact" in ch(s, treasure).types
    replay_matches(s)


def test_token_keywords_and_quoted_rule(cards):
    s = build(cards)
    src = token(s, "p1", "Piper", text='{1}: Create two 1/1 black Rat creature tokens with menace and "This token can\'t block."')
    activate(s, src)
    rats = tokens(s, "Rat")
    assert len(rats) == 2 and all(not r.tapped for r in rats)
    c = ch(s, rats[0])
    assert c.colors == {"B"} and "menace" in c.keywords and "cant_block" in scripts.statics(c)
    replay_matches(s)


def test_token_with_a_quoted_triggered_ability(cards):
    s = build(cards)
    src = token(s, "p1", "Hive", text='{1}: Create a 1/1 black and green Pest creature token with "When this token dies, you gain 1 life."')
    activate(s, src)
    (pest,) = tokens(s, "Pest")
    assert pest.token.text == "When this creature dies, you gain 1 life."
    act(s, "p1", type="set_damage", card_ids=[pest.id], delta=1)
    act(s, "p1", type="pass_priority")  # SBA: it dies — its own ability (from the quoted text) triggers
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 41
    replay_matches(s)


def test_tokens_for_each_and_where_x_is(cards):
    s = build(cards)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"zone": "battlefield"})
    src = token(s, "p1", "Druid", text="{1}: Create a 2/2 green Wolf creature token for each Forest you control.")
    activate(s, src)
    assert len(tokens(s, "Wolf")) == 3
    krenko = token(s, "p1", "Boss", text="{1}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.")
    activate(s, krenko)
    assert tokens(s, "Goblin") == []  # no Goblins yet: X is 0
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin",
                                                          "power": "1", "toughness": "1", "colors": ["R"]})
    activate(s, krenko)
    assert len(tokens(s, "Goblin")) == 2
    activate(s, krenko)
    assert len(tokens(s, "Goblin")) == 4
    replay_matches(s)


def test_named_token(cards):
    s = build(cards)
    src = token(s, "p1", "Academy", text="{1}: Create a 2/2 colorless Wizard Soldier creature token named Cadet.")
    activate(s, src)
    (cadet,) = tokens(s, "Cadet")
    assert ch(s, cadet).subtypes == {"Wizard", "Soldier"} and ch(s, cadet).colors == set()
    assert named(s, "Cadet").token.type_line == "Token Creature — Wizard Soldier"
    replay_matches(s)


def test_token_enters_tapped_and_attacking(cards):
    s = table(cards)
    raider = creature(s, "p1", "Raider", "2/2",
                      text="Whenever this creature attacks, create a 1/1 red Goblin creature token that's tapped and attacking.")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
    # the trigger resolves: only Bob can be attacked, so no question; Bob has no blockers, so
    # the table runs on through combat damage
    (goblin,) = tokens(s, "Goblin")
    assert goblin.tapped and s.state.rules.decision is None
    assert s.state.turn.phase == "main2" and s.state.players["p2"].life == 37  # 2 + 1 combat damage
    assert s.state.cards[goblin.id].attacking is None  # combat over
    assert "takes 3" in json.dumps(s.view("p2")["log"])
    replay_matches(s)


def test_attacking_token_can_be_blocked(cards):
    s = table(cards)
    raider = creature(s, "p1", "Raider", "2/2",
                      text="Whenever this creature attacks, create a 1/1 red Goblin creature token that's tapped and attacking.")
    wall = creature(s, "p2", "Wall", "0/4")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
    pass_until_stack_empty(s)
    (goblin,) = tokens(s, "Goblin")
    for _ in range(4):
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.kind == "declare_blockers" and f"a:{goblin.id}" in {o.id for o in d.options}
    block(s, "p2", (wall, goblin))
    for _ in range(6):
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 38 and s.state.cards[wall.id].damage == 1
    replay_matches(s)


def test_attacking_tokens_choose_whom_to_attack_in_multiplayer(cards):
    s = table(cards, players=3)
    raider = creature(s, "p1", "Raider", "2/2",
                      text="Whenever this creature attacks, create two 1/1 red Goblin creature tokens that are tapped and attacking.")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # 802.2: every opponent defends
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    goblins = tokens(s, "Goblin")
    assert len(goblins) == 2 and all(g.tapped for g in goblins)
    for _ in range(8):  # (nobody can block: the table runs on through combat damage)
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 38 and s.state.players["p3"].life == 38  # the Raider hit Bob, the Goblins Carol
    replay_matches(s)


def test_tokens_created_outside_combat_are_not_attacking(cards):
    s = build(cards)
    src = token(s, "p1", "Drill", text="{1}: Create a 1/1 red Goblin creature token that's tapped and attacking.")
    activate(s, src)
    (goblin,) = tokens(s, "Goblin")
    assert goblin.tapped and goblin.attacking is None  # 508.4: only during combat
    replay_matches(s)


def test_coverage_of_krenko_and_token_makers(cards):
    from app.rules import coverage

    krenko = coverage.of_card_data(cards.resolve("Krenko, Mob Boss"))
    assert krenko.level == "FULL"
    assert find(build(cards).state, "Krenko, Mob Boss", "p1") is not None
    assert zone(build(cards).state, "p1", "command")
