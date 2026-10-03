"""Target groups and divided effects (CR 115, 601.2c-d, 603.3d, 608.2b, 115.7f).

Every word "target" is its own group of targets (115.3): "up to two target creatures" (0-2),
"two target creatures" (exactly 2), "target creature and another target creature" (two groups,
distinct). The targets of each group are chosen in printed order in a private decision; a
divided group then gets its division (each target at least 1, 601.2d). On resolution each
target is checked on its own: illegal ones aren't affected (their share isn't moved: 115.7f),
and only if every chosen target is illegal does the spell or ability do nothing (608.2b).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from app.rules.scripts import parse_effects, resolve_it
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def respond_on(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def decision(s):
    return s.state.rules.decision


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)


def choose(s, ids=(), **kw):
    d = decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids), **kw)


# -- parsing ------------------------------------------------------------------------------
CREATURE = 'sel:{"types":["Creature"]}'


@pytest.mark.parametrize(("text", "groups"), [
    ("Tap up to two target creatures.", [{"what": CREATURE, "min": 0, "max": 2}]),
    ("Destroy two target creatures.", [{"what": CREATURE, "min": 2, "max": 2}]),
    ("Return one or two target creatures to their owners' hands.", [{"what": CREATURE, "min": 1, "max": 2}]),
    ("Tap any number of target creatures.", [{"what": CREATURE, "min": 0, "max": 20}]),
    ("~ deals 2 damage to each of up to three targets.", [{"what": "any", "min": 0, "max": 3}]),
    ("Destroy target artifact and target enchantment.", [{"what": 'sel:{"types":["Artifact"]}', "min": 1, "max": 1},
                                                         {"what": 'sel:{"types":["Enchantment"]}', "min": 1, "max": 1}]),
    # 115.3: two words "target", two groups (the same creature may be chosen for both)
    ("Tap target creature. Untap target creature.", [{"what": "creature", "min": 1, "max": 1},
                                                     {"what": "creature", "min": 1, "max": 1}]),
    ("Tap target creature. Untap another target creature.",
     [{"what": "creature", "min": 1, "max": 1}, {"what": CREATURE, "min": 1, "max": 1, "distinct_from": [0]}]),
    ("~ deals 2 damage to any target and 1 damage to another target.",
     [{"what": "any", "min": 1, "max": 1}, {"what": "any", "min": 1, "max": 1, "distinct_from": [0]}]),
    ("~ deals 3 damage divided as you choose among one, two, or three targets.",
     [{"what": "any", "min": 1, "max": 3, "divide": {"what": "damage", "total": 3}}]),
    ("~ deals 2 damage divided as you choose among one or two targets.",
     [{"what": "any", "min": 1, "max": 2, "divide": {"what": "damage", "total": 2}}]),
    ("~ deals 4 damage divided as you choose among any number of targets.",
     [{"what": "any", "min": 1, "max": 4, "divide": {"what": "damage", "total": 4}}]),
    ("Distribute two +1/+1 counters among one or two target creatures you control.",
     [{"what": 'sel:{"controller":"you","types":["Creature"]}', "min": 1, "max": 2,
       "divide": {"what": "counters", "total": 2}}]),
])
def test_target_groups_are_parsed(text, groups):
    effects, target, _ = parse_effects(text)
    assert target == groups
    assert all(e["who"].startswith("target:") for e in effects if e.get("who", "").startswith("target"))


def test_one_plain_target_keeps_the_old_shape():
    assert parse_effects("Tap target creature. It gets +1/+1 until end of turn.") == (
        [{"do": "tap", "who": "target"}, {"do": "pump", "who": "target", "p": 1, "t": 1}], "creature", False)
    # "Target player draws a card, then discards a card": one word "target", one target
    assert parse_effects("Target player draws a card, then discards a card.")[1] == "player"


def test_pronouns_bind_to_the_last_group():
    effects, _, _ = parse_effects("Tap up to two target creatures. Put a +1/+1 counter on each of them.")
    assert [e["who"] for e in effects] == ["target:0", "target:0"]
    effects, _, _ = parse_effects("Tap target creature. Untap target creature. It gets +1/+1 until end of turn.")
    assert effects[-1]["who"] == "target:1"  # "it": the last target named
    # "it" after a group of several targets: which one? (manual)
    assert parse_effects("Tap up to two target creatures. Put a +1/+1 counter on it.") is None
    assert resolve_it([{"do": "tap", "who": "them"}], "self", []) is None  # "them" with nothing before it


@pytest.mark.parametrize("text", [
    "~ deals X damage divided as you choose among any number of target creatures, where X is its power.",
    "Exile two target cards from an opponent's graveyard.",  # (the same opponent's? not a guess)
    # "with flying" qualifies only the creature (any artifact can be chosen): a selector can't say that
    "Destroy up to one target artifact, enchantment, or creature with flying.",
    "Destroy target artifact, enchantment, or creature with flying.",
    "~ deals 2 damage to another target.",  # ("another" than what?)
])
def test_unsupported_wordings(text):
    assert parse_effects(text) is None


def test_cards_with_groups_are_full(cards):
    for name in ("Test Barrage", "Test Double Tap"):
        data = cards.get(cards.resolve(name)["id"])
        assert coverage.of_characteristics(printed_from_data(data)).level == "FULL", name


# -- choosing (601.2c) -----------------------------------------------------------------------
def test_exact_number_of_targets(cards):
    s = build(cards)
    a, b, c = (token(s, "p2", n) for n in ("Ant", "Bee", "Cat"))
    src = token(s, "p1", "Tapper", text="{1}: Tap two target creatures.")
    activate(s, src)
    d = decision(s)
    assert (d.kind, d.min_choices, d.max_choices) == ("choose_cards", 2, 2) and {a.id, b.id, c.id} <= {o.id for o in d.options}
    assert s.view("p2")["rules"]["decision"].get("options") is None  # privacy: only the chooser sees them
    with pytest.raises(ActionError):
        choose(s, [a.id])
    choose(s, [a.id, b.id])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped and not s.state.cards[c.id].tapped
    replay_matches(s)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_up_to_n_targets(cards, n):
    s = build(cards)
    creatures = [token(s, "p2", name) for name in ("Ant", "Bee", "Cat")]
    src = token(s, "p1", "Tapper", text="{1}: Tap up to two target creatures.")
    activate(s, src)
    d = decision(s)
    assert (d.min_choices, d.max_choices) == (0, 2)
    choose(s, [c.id for c in creatures[:n]])  # 115.6: zero targets is a choice too
    pass_until_stack_empty(s)
    assert [s.state.cards[c.id].tapped for c in creatures] == [k < n for k in range(3)]
    assert not s.state.rules.stack
    replay_matches(s)


def test_targets_given_up_front_with_counts(cards):
    s = build(cards)
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    src = token(s, "p1", "Tapper", text="{1}: Tap up to two target creatures.")
    activate(s, src, targets=[a.id, b.id], target_counts=[2])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped
    replay_matches(s)


def test_the_same_target_twice_for_one_word_target_is_refused(cards):
    s = build(cards)
    a = token(s, "p2", "Ant")
    token(s, "p2", "Bee")
    src = token(s, "p1", "Tapper", text="{1}: Tap up to two target creatures.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="twice"):  # 115.3
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[a.id, a.id], target_counts=[2])
    with pytest.raises(ActionError, match="right number"):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[a.id], target_counts=[2])
    with pytest.raises(ActionError, match="Choose 0 to 2"):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[a.id, a.id, a.id], target_counts=[3])


def test_the_same_object_for_two_words_target(cards):
    """115.3 / 601.2c: "Tap target creature. Put a +1/+1 counter on target creature." — two
    words "target": the same creature may be chosen for each."""
    s = build(cards)
    bear = token(s, "p2", "Bear")
    src = token(s, "p1", "Twice", text="{1}: Tap target creature. Put a +1/+1 counter on target creature.")
    activate(s, src)
    assert decision(s).resume["step"] == "cast_group"
    choose(s, [bear.id])
    d = decision(s)
    assert bear.id in {o.id for o in d.options} and "group 2 of 2" in d.prompt
    choose(s, [bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters.get("+1/+1") == 1
    replay_matches(s)


def test_another_target_cant_be_the_first_one(cards):
    s = build(cards)
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    act(s, "p2", type="tap", card_ids=[b.id], tapped=True)
    src = token(s, "p1", "Switch", text="{1}: Tap target creature. Untap another target creature.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="Another target"):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[a.id, a.id], target_counts=[1, 1])
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    choose(s, [a.id])
    assert a.id not in {o.id for o in decision(s).options}  # "another": the first target isn't offered
    choose(s, [b.id])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    replay_matches(s)


def test_a_spell_whose_lines_each_target(cards):
    """Test Double Tap: "Tap target creature. Untap another target creature." / "Draw a card."."""
    s = build(cards, "Test Double Tap")
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    act(s, "p2", type="tap", card_ids=[b.id], tapped=True)
    spell = to_hand(s, "Test Double Tap")
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id, b.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + 1
    replay_matches(s)


# -- resolution (608.2b) ------------------------------------------------------------------------
def test_one_illegal_target_the_others_are_still_affected(cards):
    s = build(cards)
    respond_on(s)
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    src = token(s, "p1", "Tapper", text="{1}: Tap two target creatures. You gain 3 life.")
    activate(s, src, targets=[a.id, b.id], target_counts=[2])
    act(s, "p2", type="move", card_ids=[a.id], to={"zone": "graveyard"})  # the Ant is gone
    pass_until_stack_empty(s)
    assert s.state.cards[b.id].tapped and s.state.players["p1"].life == 43
    replay_matches(s)


def test_all_targets_illegal_it_does_nothing(cards):
    s = build(cards)
    respond_on(s)
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    src = token(s, "p1", "Tapper", text="{1}: Tap two target creatures. You gain 3 life.")
    activate(s, src, targets=[a.id, b.id], target_counts=[2])
    act(s, "p2", type="move", card_ids=[a.id, b.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 40  # 608.2b: it doesn't resolve at all
    assert not s.state.rules.stack
    replay_matches(s)


def test_zero_targets_chosen_resolves_normally(cards):
    s = build(cards)
    src = token(s, "p1", "Tapper", text="{1}: Tap up to two target creatures. You gain 3 life.")
    activate(s, src, targets=[], target_counts=[0])
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 43  # 115.6: not targeted, nothing to check
    replay_matches(s)


# -- divided damage and counters (601.2d, 115.7f) -------------------------------------------------
def test_divided_damage_is_asked_after_the_targets(cards):
    s = build(cards, "Test Barrage")
    ogre = token(s, "p2", "Ogre", "3/3")
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = decision(s)
    assert (d.kind, d.min_choices, d.max_choices) == ("choose_cards", 1, 3)
    choose(s, [ogre.id, "p2"])
    d = decision(s)
    assert d.kind == "divide" and [o.id for o in d.options] == [ogre.id, "p2"] and d.display["total"] == 4
    view = s.view("p2")["rules"]["decision"]
    assert view["kind"] == "waiting" and view.get("options") is None and view.get("display") is None  # privacy
    for bad in ([2, 1], [4, 0], [1, 1, 2]):  # the total, at least 1 each, one amount per target
        with pytest.raises(ActionError, match="Divide 4"):
            choose(s, amounts=bad)
    with pytest.raises(ActionError):
        choose(s, [ogre.id])
    choose(s, amounts=[3, 1])
    pass_until_stack_empty(s)
    assert ogre.id not in s.state.cards and s.state.players["p2"].life == 39
    replay_matches(s)


def test_one_target_gets_all_of_it(cards):
    s = build(cards, "Test Barrage")
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], target_counts=[1])  # no division asked
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 36
    replay_matches(s)


def test_division_given_up_front_and_limits(cards):
    s = build(cards, "Test Barrage")
    ants = [token(s, "p2", f"Ant{i}", "1/1") for i in range(4)]
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    with pytest.raises(ActionError, match="Choose 1 to 3"):  # "one, two, or three targets"
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[a.id for a in ants], target_counts=[4])
    with pytest.raises(ActionError, match="Divide 4"):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ants[0].id, "p2"], target_counts=[2], division=[1, 1])
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ants[0].id, ants[1].id, "p2"], target_counts=[3],
        division=[1, 1, 2])
    pass_until_stack_empty(s)
    assert ants[0].id not in s.state.cards and ants[1].id not in s.state.cards and s.state.players["p2"].life == 38
    replay_matches(s)


def test_an_illegal_targets_share_isnt_reassigned(cards):
    """115.7f / 608.2b: the division stays as announced; the illegal target's damage is lost."""
    s = build(cards, "Test Barrage")
    respond_on(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ogre.id, "p2"], target_counts=[2], division=[3, 1])
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "graveyard"})
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 39  # only its own 1
    replay_matches(s)


def test_distributed_counters(cards):
    s = build(cards)
    a, b = token(s, "p1", "Ant"), token(s, "p1", "Bee")
    src = token(s, "p1", "Armory", text="{1}: Distribute three +1/+1 counters among one, two, or three target creatures you control.")
    activate(s, src)
    choose(s, [a.id, b.id])
    choose(s, amounts=[2, 1])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].counters.get("+1/+1") == 2 and s.state.cards[b.id].counters.get("+1/+1") == 1
    replay_matches(s)


# -- triggered abilities (603.3d) -----------------------------------------------------------------
def enter_a_soldier(s):
    """Something enters (a token made by an ability; a token made by hand triggers nothing)."""
    src = token(s, "p1", "Muster", text="{1}: Create a 1/1 white Soldier creature token.")
    activate(s, src)
    pass_until_stack_empty(s)


def test_a_trigger_with_two_target_groups(cards):
    s = build(cards)
    a, b = token(s, "p2", "Ant"), token(s, "p2", "Bee")
    act(s, "p2", type="tap", card_ids=[b.id], tapped=True)
    token(s, "p1", "Herald", text="Whenever another creature you control enters, tap target creature. "
                                  "Untap another target creature.")
    enter_a_soldier(s)
    d = decision(s)
    assert d.resume["step"] == "trigger_group" and d.player == "p1"
    assert s.view("p2")["rules"]["decision"].get("options") is None
    choose(s, [a.id])
    assert a.id not in {o.id for o in decision(s).options}
    choose(s, [b.id])
    pass_until_stack_empty(s)
    assert s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    replay_matches(s)


def test_a_divided_trigger(cards):
    s = build(cards)
    ogre = token(s, "p2", "Ogre", "2/2")
    token(s, "p1", "Titan", "6/6", text="Whenever another creature you control enters, ~ deals 3 damage divided as "
                                         "you choose among one, two, or three targets.")
    enter_a_soldier(s)
    choose(s, [ogre.id, "p2"])
    assert decision(s).kind == "divide" and decision(s).resume["step"] == "trigger_divide"
    choose(s, amounts=[2, 1])
    pass_until_stack_empty(s)
    assert ogre.id not in s.state.cards and s.state.players["p2"].life == 39
    replay_matches(s)


def test_a_trigger_without_enough_legal_targets_is_removed(cards):
    s = build(cards)
    token(s, "p1", "Pair", text="Whenever another creature you control enters, tap two target artifacts.")
    enter_a_soldier(s)
    assert decision(s) is None and not s.state.rules.stack  # 603.3d
    assert "doesn't have enough legal targets" in str(s.view("p1")["log"])
    replay_matches(s)
