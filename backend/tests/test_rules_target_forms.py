"""Target forms (CR 115, 601.2c, 608.2b): "target player or planeswalker", "other" inside a counted
group ("up to one other target creature", "each of up to two other targets", "any other target"),
"target creature or Vehicle" (a type or a subtype), an activated or triggered ability on the stack
as a target (115.1c-d, 701.6), "exile [targets] until ~ leaves the battlefield" for any target
phrase (610.3c), counters on several target phrases, and the refusals the grammar registers
(app/rules/coverage.py REFUSED): "fights" and "choose … target" until their primitives exist,
stun counters, "target player's graveyard", "for each target beyond the first" …
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, effects, language, scripts, selectors, targets
from app.rules.plan import Plan
from app.rules.scripts import parse_effects
from tests.game_helpers import act
from tests.test_rules_attachments import build, mana, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_multitarget import activate, choose, decision, respond_on
from tests.test_rules_suspend import until

CREATURE = 'sel:{"types":["Creature"]}'
OTHER_CREATURE = 'sel:{"other":true,"types":["Creature"]}'
CREATURE_OR_VEHICLE = 'sel:{"subtypes":["Vehicle"],"types":["Creature"],"union":true}'
ANY_ABILITY = 'sel:{"ability":"any","zones":["stack"]}'


def ch(s, card):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def artifact_token(s, pid, name, subtype=None):
    """A noncreature artifact token (a Vehicle when ``subtype`` says so)."""
    type_line = "Token Artifact" + (f" — {subtype}" if subtype else "")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "text": ""})
    return named(s, name)


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("phrase", "fields"), [
    ("creature or Vehicle", {"types": ("Creature",), "subtypes": ("Vehicle",), "union": True}),
    ("creature or Vehicle you control", {"union": True, "controller": "you"}),
    ("creature or Vehicle card from your graveyard", {"union": True, "card": True, "zones": ("graveyard",)}),
    ("activated or triggered ability", {"ability": "any", "zones": ("stack",)}),
    ("activated ability", {"ability": "activated", "zones": ("stack",)}),
    ("triggered ability you control", {"ability": "triggered", "zones": ("stack",), "controller": "you"}),
    ("artifact or creature an opponent controls", {"types": ("Creature", "Artifact"), "union": False}),
])
def test_selectors(phrase, fields):
    sel = selectors.parse(phrase)
    assert sel is not None, phrase
    for k, v in fields.items():
        assert getattr(sel, k) == v, (phrase, k)
    assert selectors.from_key(sel.key()) == sel


@pytest.mark.parametrize("phrase", [
    "activated ability from an artifact source",  # (the source's qualities aren't read)
    "activated or triggered ability from your graveyard", "artifact creature or Vehicle",
])
def test_refused_selectors(phrase):
    assert selectors.parse(phrase) is None


@pytest.mark.parametrize(("text", "effects_", "target"), [
    # a player, or any planeswalker (whoever controls it)
    ("~ deals 4 damage to target player or planeswalker.", [{"do": "damage", "who": "target", "n": 4}], "player_or_planeswalker"),
    ("~ deals 3 damage to target player or planeswalker and 3 damage to target creature.",
     [{"do": "damage", "who": "target:0", "n": 3}, {"do": "damage", "who": "target:1", "n": 3}],
     [{"what": "player_or_planeswalker", "min": 1, "max": 1}, {"what": CREATURE, "min": 1, "max": 1}]),
    # "other" inside a counted group: other than the source when nothing was targeted before …
    ("Up to one other target creature gets -3/-0 until end of turn.", [{"do": "pump", "who": "target:0", "p": -3, "t": 0}],
     [{"what": OTHER_CREATURE, "min": 0, "max": 1}]),
    ("Put a +1/+1 counter on each of up to two other target creatures.", [{"do": "add_counters", "who": "target:0", "kind": "+1/+1", "n": 1}],
     [{"what": OTHER_CREATURE, "min": 0, "max": 2}]),
    ("Return up to two other target nonland permanents to their owners' hands.", [{"do": "bounce", "who": "target:0"}],
     [{"what": 'sel:{"not_types":["Land"],"other":true}', "min": 0, "max": 2}]),
    # … and distinct from the earlier target (115.3) when there is one
    ("~ deals 4 damage to any target and 3 damage to each of up to two other targets.",
     [{"do": "damage", "who": "target:0", "n": 4}, {"do": "damage", "who": "target:1", "n": 3}],
     [{"what": "any", "min": 1, "max": 1}, {"what": "any", "min": 0, "max": 2, "distinct_from": [0]}]),
    ("~ deals 2 damage to any target and 1 damage to any other target.",
     [{"do": "damage", "who": "target:0", "n": 2}, {"do": "damage", "who": "target:1", "n": 1}],
     [{"what": "any", "min": 1, "max": 1}, {"what": "any", "min": 1, "max": 1, "distinct_from": [0]}]),
    ("Tap target creature. Tap up to one other target creature.", [{"do": "tap", "who": "target:0"}, {"do": "tap", "who": "target:1"}],
     [{"what": "creature", "min": 1, "max": 1}, {"what": CREATURE, "min": 0, "max": 1, "distinct_from": [0]}]),
    # a type or a subtype
    ("Destroy target creature or Vehicle.", [{"do": "destroy", "who": "target"}], CREATURE_OR_VEHICLE),
    # abilities on the stack
    ("Counter target activated or triggered ability.", [{"do": "counter", "who": "target"}], ANY_ABILITY),
    ("Counter target activated ability.", [{"do": "counter", "who": "target"}], 'sel:{"ability":"activated","zones":["stack"]}'),
    ("Counter up to one target activated or triggered ability.", [{"do": "counter", "who": "target:0"}],
     [{"what": ANY_ABILITY, "min": 0, "max": 1}]),
    # "until ~ leaves the battlefield" for any target phrase (610.3c)
    ("Exile target artifact or creature an opponent controls until ~ leaves the battlefield.",
     [{"do": "exile_until", "who": "target"}], 'sel:{"controller":"opponent","types":["Creature","Artifact"]}'),
    ("Exile up to one target nonland permanent an opponent controls until ~ leaves the battlefield. You gain 2 life.",
     [{"do": "exile_until", "who": "target:0"}, {"do": "gain_life", "who": "you", "n": 2}],
     [{"what": 'sel:{"controller":"opponent","not_types":["Land"]}', "min": 0, "max": 1}]),
    # counters on two target phrases: one group each (115.3)
    ("Put a +1/+1 counter on up to one target land and up to one target creature.",
     [{"do": "add_counters", "who": "target:0", "kind": "+1/+1", "n": 1}, {"do": "add_counters", "who": "target:1", "kind": "+1/+1", "n": 1}],
     [{"what": 'sel:{"types":["Land"]}', "min": 0, "max": 1}, {"what": CREATURE, "min": 0, "max": 1}]),
])
def test_target_forms_are_parsed(text, effects_, target):
    assert parse_effects(text) == (effects_, target, False)


@pytest.mark.parametrize("text", [
    "~ deals 2 damage to any other target.",  # ("other" than what? nothing was targeted before)
    "Tap each of up to two other targets.",
    "~ deals 1 damage to any target, 2 damage to another target, and 3 damage to a third target.",  # (three-way: not read)
    "Counter target creature.",  # (a permanent can't be countered, 701.6a)
    "Counter target activated or triggered ability from an artifact or enchantment source.",
    "Exile target player's graveyard.",  # (a target player's zone as the objects: not modelled)
    "Exile it until ~ leaves the battlefield.",
    "Target player shuffles up to four target cards from their graveyard into their library.",
    "Tap up to X target creatures.",
])
def test_refused_forms(text):
    assert parse_effects(text) is None


def test_refusals_are_registered():
    """Every refused wording names why (the missing piece), so the gap report can rank it."""
    for text, piece in [
        ("Target creature you control fights another target creature.", "fight"),
        ("Choose up to one target creature. That creature can't block this turn.", "choose_targets"),
        ("This spell costs {1}{U} more to cast for each target beyond the first.", "extra target"),
        ("Exile target player's graveyard.", "zone"),
        ("Destroy target creature that player controls.", "named earlier"),
        ("Destroy up to X target artifacts.", "variable number"),
        # (copy system, wave 2F: "Copy target activated or triggered ability you control." is read now —
        # tests/test_rules_copy.py; copying the spell a trigger was about is still refused)
        ("Whenever you cast an instant or sorcery spell, copy it.", "copying"),
        ("Target player shuffles up to four target cards from their graveyard into their library.", "earlier target"),
        ("Switch target creature's power and toughness until end of turn.", "P/T"),
    ]:
        reason = coverage.refusal(text)
        assert reason is not None and piece in reason, text
        assert parse_effects(text) is None or language.has_primitive(piece), text
    assert coverage.refusal("Destroy target creature.") is None


# -- the primitives another module must add: the grammar is ready, the wording is refused until then
def test_fight_grammar_now_has_its_primitive():
    text = "Target creature you control fights another target creature."
    assert "fight" in effects.PRIMITIVES  # (agent G: app/rules/effects.fight)
    assert parse_effects(text) == ([{"do": "fight", "who": "target:0", "with": "target:1"}], [
        {"what": 'sel:{"controller":"you","types":["Creature"]}', "min": 1, "max": 1},
        {"what": CREATURE, "min": 1, "max": 1, "distinct_from": [0]}], False)  # 115.3: "another": not the first
    assert parse_effects("It fights up to one target creature you don't control.", it="self") == (  # "When ~ enters, it fights …"
        [{"do": "fight", "who": "self", "with": "target:0"}],
        [{"what": 'sel:{"controller":"opponent","types":["Creature"]}', "min": 0, "max": 1}], False)
    assert parse_effects("~ fights target creature an opponent controls.") == (
        [{"do": "fight", "who": "self", "with": "target"}], 'sel:{"controller":"opponent","types":["Creature"]}', False)
    assert parse_effects("~ fights any target.") is None  # (only creatures fight, 701.14a)
    assert parse_effects("~ fights each creature you don't control.") is None


def test_choose_targets_grammar_now_has_its_primitive():
    text = "Choose up to one target creature. That creature can't block this turn."
    assert "choose_targets" in effects.PRIMITIVES  # (agent G: app/rules/effects.choose_targets)
    assert parse_effects(text) == ([{"do": "choose_targets", "who": "target:0"}, {"do": "restrict", "who": "target:0", "rules": ["cant_block"]}],
                                   [{"what": CREATURE, "min": 0, "max": 1}], False)
    assert parse_effects("Choose two target creatures. Untap them. Put two +1/+1 counters on each of them.") == (
        [{"do": "choose_targets", "who": "target:0"}, {"do": "untap", "who": "target:0"},
         {"do": "add_counters", "who": "target:0", "kind": "+1/+1", "n": 2}], [{"what": CREATURE, "min": 2, "max": 2}], False)
    assert parse_effects("Choose a creature you control.") is None  # (not a target: the player-choices grammar)


def test_choose_targets_binds_a_later_pronoun_end_to_end(cards):
    """With the (no-op) primitive in place, "Choose up to one target creature. That creature can't
    block this turn." targets on activation (601.2c) and the second sentence acts on the target."""
    scripts._cached.cache_clear()
    s = build(cards)
    wall = token(s, "p2", "Wall", "0/4")
    src = token(s, "p1", "Pointer", text="{1}: Choose up to one target creature. That creature can't block this turn.")
    activate(s, src)
    d = decision(s)
    assert (d.min_choices, d.max_choices) == (0, 1) and wall.id in {o.id for o in d.options}
    assert s.view("p2")["rules"]["decision"].get("options") is None  # only the chooser sees the candidates
    choose(s, [wall.id])
    pass_until_stack_empty(s)
    assert "cant_block" in ch(s, wall).imposed
    replay_matches(s)
    scripts._cached.cache_clear()


def test_fight_targets_end_to_end(cards):
    """The two words "target" of "… fights another target creature" are two groups; the second
    can't be the first's object (115.3); each deals damage equal to its power to the other (701.14a)."""
    scripts._cached.cache_clear()
    s = build(cards)
    mine, theirs = token(s, "p1", "Mine", "3/3"), token(s, "p2", "Theirs", "2/2")
    src = token(s, "p1", "Pit", text="{1}: Target creature you control fights another target creature.")
    activate(s, src)
    choose(s, [mine.id])
    d = decision(s)
    assert mine.id not in {o.id for o in d.options} and theirs.id in {o.id for o in d.options}
    choose(s, [theirs.id])
    pass_until_stack_empty(s)
    assert s.state.cards[mine.id].damage == 2 and theirs.id not in s.state.cards  # (a 2/2 token dealt 3 dies)
    replay_matches(s)
    scripts._cached.cache_clear()


# -- choosing and resolving ---------------------------------------------------------------------
def walker(s):
    """A planeswalker on Alice's battlefield with 3 loyalty (put there by hand, so its counters too)."""
    card = named(s, "Test Walker Card")
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[card.id], kind="loyalty", delta=3)
    return card


def build_with_bob(cards, *bob_names):
    """A table where Bob's deck holds real cards (a token that leaves the battlefield ceases to
    exist, 704.5d: exile-and-return needs cards)."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob_names), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for name in bob_names:
        act(s, "p2", type="move", card_ids=[named(s, name).id], to={"zone": "battlefield"})
    return s


def test_target_player_or_planeswalker(cards):
    s = build(cards, "Test Walker Card")
    w = walker(s)
    bear = token(s, "p2", "Bear")
    src = token(s, "p1", "Slinger", text="{1}: ~ deals 2 damage to target player or planeswalker.")
    activate(s, src)
    d = decision(s)
    options = {o.id for o in d.options}
    assert {"p1", "p2", w.id} <= options and bear.id not in options  # players and any planeswalker, not a creature
    choose(s, [w.id])
    pass_until_stack_empty(s)
    assert s.state.cards[w.id].counters.get("loyalty") == 1  # 120.3c: damage removes loyalty
    replay_matches(s)


def test_target_opponent_or_planeswalker(cards):
    s = build(cards, "Test Walker Card")
    w = walker(s)
    src = token(s, "p1", "Slinger", text="{1}: ~ deals 2 damage to target opponent or planeswalker.")
    activate(s, src)
    options = {o.id for o in decision(s).options}
    assert "p1" not in options and {"p2", w.id} <= options  # not yourself; your own planeswalker still qualifies
    choose(s, ["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_other_target_creature_is_not_the_source(cards):
    s = build(cards)
    ally, enemy = token(s, "p1", "Ally"), token(s, "p2", "Enemy")
    src = token(s, "p1", "Captain", text="{1}: Up to one other target creature gets +2/+2 until end of turn.")
    activate(s, src)
    options = {o.id for o in decision(s).options}
    assert src.id not in options and {ally.id, enemy.id} <= options
    choose(s, [ally.id])
    pass_until_stack_empty(s)
    assert ch(s, ally).pt == (4, 4)
    replay_matches(s)


def test_any_other_target_is_distinct_from_the_first(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre", "3/3")
    src = token(s, "p1", "Forker", text="{1}: ~ deals 2 damage to any target and 1 damage to any other target.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="Another target"):  # 115.3
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=["p2", "p2"], target_counts=[1, 1])
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    choose(s, ["p2"])
    d = decision(s)
    assert "p2" not in {o.id for o in d.options} and ogre.id in {o.id for o in d.options}
    choose(s, [ogre.id])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38 and s.state.cards[ogre.id].damage == 1
    replay_matches(s)


def test_each_of_up_to_two_other_targets_may_be_zero(cards):
    s = build(cards)
    src = token(s, "p1", "Dragon", "4/4", text="{1}: ~ deals 4 damage to any target and 3 damage to each of up to two other targets.")
    activate(s, src, targets=["p2"], target_counts=[1, 0])  # 115.6: none for the second group
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 36
    replay_matches(s)


def test_creature_or_vehicle(cards):
    """"target creature or Vehicle": a creature, or an artifact with the Vehicle subtype — not
    any other artifact."""
    s = build(cards)
    bear = token(s, "p2", "Bear")
    car = artifact_token(s, "p2", "Car", "Vehicle")
    rock = artifact_token(s, "p2", "Rock")
    src = token(s, "p1", "Wrecker", text="{1}: Destroy target creature or Vehicle.")
    activate(s, src)
    options = {o.id for o in decision(s).options}
    assert {bear.id, car.id} <= options and rock.id not in options
    choose(s, [car.id])
    pass_until_stack_empty(s)
    assert car.id not in s.state.cards and rock.id in s.state.cards
    replay_matches(s)


def test_exile_until_it_leaves_for_any_target_phrase(cards):
    """610.3c with a target phrase only the selector grammar reads, and "up to one": the exiled
    artifact returns when the source leaves."""
    s = build_with_bob(cards, "Sol Ring")
    rock = named(s, "Sol Ring")
    bear = token(s, "p2", "Bear")
    src = token(s, "p1", "Jailer", text="{1}: Exile up to one target artifact or creature an opponent controls until ~ leaves the battlefield.")
    activate(s, src)
    options = {o.id for o in decision(s).options}
    assert {rock.id, bear.id} <= options and src.id not in options
    choose(s, [rock.id])
    pass_until_stack_empty(s)
    assert s.state.cards[rock.id].zone == "p2:exile"
    act(s, "p1", type="set_damage", card_ids=[src.id], value=2)  # the Jailer dies (704.5g) → the Ring comes back
    act(s, "p1", type="pass_priority")
    until(s, lambda s: s.state.cards[rock.id].zone == "p2:battlefield", limit=20)
    assert s.state.cards[rock.id].zone == "p2:battlefield" and src.id not in s.state.cards
    replay_matches(s)


def test_exile_until_one_of_two_targets_gone(cards):
    """608.2b: the target that left isn't affected; the other is exiled."""
    s = build_with_bob(cards, "Grizzly Bears")
    respond_on(s)
    a, b = token(s, "p2", "Ant"), named(s, "Grizzly Bears")
    # ("… creatures an opponent controls" for several targets stays refused: the same opponent's? — see target_group)
    src = token(s, "p1", "Jailer", text="{1}: Exile up to two target creatures you don't control until ~ leaves the battlefield.")
    activate(s, src, targets=[a.id, b.id], target_counts=[2])
    act(s, "p2", type="move", card_ids=[a.id], to={"zone": "graveyard"})  # (a token: it ceases to exist there)
    pass_until_stack_empty(s)
    assert s.state.cards[b.id].zone == "p2:exile" and a.id not in s.state.cards
    replay_matches(s)


def activate_as(s, pid, card, target=None):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=0, **({"targets": [target]} if target else {}))


def test_counter_target_activated_ability(cards):
    """An activated ability on the stack is a legal target (115.1c); countered, it stops existing
    (701.6) and its effect never happens. Spells and triggered abilities aren't offered."""
    s = build(cards)
    respond_on(s)  # (nobody passes automatically: the ability waits on the stack)
    bear = token(s, "p2", "Bear")
    grower = token(s, "p2", "Grower", text="{1}: Target creature you control gets +3/+3 until end of turn.")
    stifler = token(s, "p1", "Stifler", text="{1}: Counter target activated ability.")
    act(s, "p1", type="pass_priority")  # Bob gets priority in Alice's main phase
    assert s.state.rules.priority == "p2"
    activate_as(s, "p2", grower, bear.id)
    ability = next(c for c in s.state.cards.values() if c.zone == "stack" and c.ability is not None)
    plan = Plan(s.state, "p1", cards, None)
    assert targets.legal_targets(plan, ANY_ABILITY, "p1") == [ability.id]
    assert targets.legal_targets(plan, 'sel:{"ability":"triggered","zones":["stack"]}', "p1") == []
    assert s.state.rules.priority == "p1"  # (Bob's ability on the stack: Alice may respond)
    activate_as(s, "p1", stifler)
    d = decision(s)
    assert [o.id for o in d.options] == [ability.id] and s.view("p2")["rules"]["decision"].get("options") is None
    choose(s, [ability.id])
    pass_until_stack_empty(s)
    assert ability.id not in s.state.cards and not s.state.zones.get("stack")
    assert ch(s, bear).pt == (2, 2)  # the countered ability never resolved
    replay_matches(s)


def test_an_ability_cant_be_countered_by_a_spell_counter(cards):
    """"Counter target spell" never offers an ability (115.2), and an ability counter never offers a spell."""
    s = build(cards)
    respond_on(s)
    grower = token(s, "p2", "Grower", text="{1}: You gain 3 life.")
    act(s, "p1", type="pass_priority")
    activate_as(s, "p2", grower)
    ability = next(c for c in s.state.cards.values() if c.zone == "stack" and c.ability is not None)
    plan = Plan(s.state, "p1", cards, None)
    assert targets.legal_targets(plan, "spell", "p1") == []
    assert targets.legal_targets(plan, 'sel:{"zones":["stack"]}', "p1") == []  # "target spell" as a selector
    assert targets.legal_targets(plan, ANY_ABILITY, "p1") == [ability.id]


def test_counters_on_two_target_phrases(cards):
    s = build(cards)
    forest = named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    bear = token(s, "p1", "Bear")
    src = token(s, "p1", "Omo", text="{1}: Put a +1/+1 counter on up to one target land and up to one target creature.")
    activate(s, src)
    d = decision(s)
    assert forest.id in {o.id for o in d.options} and bear.id not in {o.id for o in d.options}
    choose(s, [forest.id])
    d = decision(s)
    assert bear.id in {o.id for o in d.options} and forest.id not in {o.id for o in d.options}
    choose(s, [bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[forest.id].counters == {"+1/+1": 1} and s.state.cards[bear.id].counters == {"+1/+1": 1}
    replay_matches(s)


# -- "counter [target … spell] unless its controller pays" through the generic grammar -----------------
def test_counter_a_selector_spell_unless_its_controller_pays(cards):
    """"Counter target red spell unless its controller pays {2}." (a spell, so its bindings are
    renamed per line): the Bolt's controller is offered the payment; paid, the Bolt resolves."""
    from tests.test_rules_counter import bolt_then_answer
    from tests.test_rules_counter import build as build_counter

    s, bolt, denial = build_counter(cards, "Test Red Denial")
    assert coverage.of_characteristics(ch(s, denial)).level == "FULL"
    mana(s, C=2)  # (the payment is only offered to a payer who can pay it now)
    bolt_then_answer(s, bolt, denial, U=1)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    assert d.kind == "choose_one" and "pay {2}" in d.prompt
    assert s.view("p2")["rules"]["decision"].get("options") is None  # Alice's choice, privately
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"


def test_mana_value_of_a_spell_on_the_stack_counts_x(cards):
    """202.3e: while a spell with {X} in its cost is on the stack, X is the value chosen for it —
    "target spell with mana value 1" sees Endless One cast for X=1, not for X=2."""
    from tests.test_rules_attachments import to_hand

    mv1 = 'sel:{"compare":[["mv","==",1]],"zones":["stack"]}'
    for x, seen in ((1, True), (2, False)):
        s = build(cards, "Endless One")
        respond_on(s)
        one = to_hand(s, "Endless One")
        mana(s, C=x)
        act(s, "p1", type="cast_spell", card_id=one.id, x_value=x)
        assert s.state.cards[one.id].zone == "stack"
        plan = Plan(s.state, "p2", cards, None)
        assert (targets.legal_targets(plan, mv1, "p2") == [one.id]) is seen, x


def test_counter_a_selector_spell_unless_declined(cards):
    from tests.test_rules_counter import bolt_then_answer
    from tests.test_rules_counter import build as build_counter

    s, bolt, denial = build_counter(cards, "Test Red Denial")
    mana(s, C=2)
    bolt_then_answer(s, bolt, denial, U=1)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["decline"])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.players["p2"].life == 40 and s.state.cards[bolt.id].zone == "p1:graveyard"
