"""Selector grammar, second round: combat statuses ("attacking or blocking", "defending player
controls" — CR 506.3, 508.5, 508.5a), "from a single graveyard" as a constraint on a group of
targets (400.1), tokens / commanders as nouns, "N/N creature", "that's <color>", "other than ~".
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import language
from app.rules import selectors as S
from app.rules.plan import Plan
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, token
from tests.test_rules_combat import attack, automate, block, creature, decision, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

CARD_IN_GRAVEYARD = 'sel:{"card":true,"zones":["graveyard"]}'


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("phrase", "fields"), [
    ("attacking or blocking creature", {"types": ("Creature",), "in_combat": True, "attacking": False, "blocking": False}),
    ("attacking or blocking creature with flying", {"in_combat": True, "with_keywords": ("flying",)}),
    ("attacking or blocking Spirit", {"subtypes": ("Spirit",), "in_combat": True}),
    ("black or red creature that's attacking or blocking", {"colors": ("R", "B"), "in_combat": True}),
    ("creature defending player controls", {"types": ("Creature",), "controller": "defending"}),
    ("artifact or enchantment defending player controls", {"types": ("Enchantment", "Artifact"), "controller": "defending"}),
    ("creature defending player controls with toughness 2 or less", {"controller": "defending", "compare": (("toughness", "<=", 2),)}),
    ("creature token", {"types": ("Creature",), "token": True}),
    ("token you control", {"types": (), "token": True, "controller": "you"}),
    ("token an opponent controls", {"token": True, "controller": "opponent"}),
    ("Incubator token", {"subtypes": ("Incubator",), "token": True}),
    ("commander", {"types": (), "commander": True}),
    ("commander you own", {"commander": True, "owner": "you"}),
    ("1/1 creature", {"types": ("Creature",), "compare": (("power", "==", 1), ("toughness", "==", 1))}),
    ("1/1 creature you control", {"controller": "you", "compare": (("power", "==", 1), ("toughness", "==", 1))}),
    ("creature or planeswalker that's black or red", {"types": ("Planeswalker", "Creature"), "colors": ("B", "R")}),
    ("creature that's green", {"types": ("Creature",), "colors": ("G",)}),
    ("permanent that's one or more colors", {"types": (), "colorless": False}),
    ("creature other than ~", {"types": ("Creature",), "other": True}),
    ("nonland permanent other than ~", {"not_types": ("Land",), "other": True}),
    ("land you control that's tapped", {"types": ("Land",), "controller": "you", "tapped": True}),
    ("creature you control that's untapped", {"controller": "you", "tapped": False}),
    ("creature that's attacking you", {"attacking": True, "extras": ("attacking_you",)}),
    ("creature without flying that's attacking you", {"attacking": True, "without_keywords": ("flying",), "extras": ("attacking_you",)}),
    ("card from a single graveyard", {"card": True, "zones": ("graveyard",), "zone_owner": None, "extras": ("single_graveyard",)}),
    ("creature card from graveyards", {"card": True, "types": ("Creature",), "zones": ("graveyard",), "zone_owner": None}),
])
def test_parse(phrase, fields):
    sel = S.parse(phrase)
    assert sel is not None, phrase
    for k, v in fields.items():
        assert getattr(sel, k) == v, (phrase, k)
    assert S.from_key(sel.key()) == sel  # round trip


def test_keys_stay_compact():
    assert S.parse("attacking or blocking creature").key() == 'sel:{"in_combat":true,"types":["Creature"]}'
    assert S.parse("creature defending player controls").key() == 'sel:{"controller":"defending","types":["Creature"]}'
    assert S.parse("creature token").key() == 'sel:{"token":true,"types":["Creature"]}'
    # keys of phrases the old grammar read are unchanged
    assert S.parse("attacking creature").key() == 'sel:{"attacking":true,"types":["Creature"]}'
    assert S.parse("nontoken creature").key() == 'sel:{"token":false,"types":["Creature"]}'


@pytest.mark.parametrize("phrase", [
    "nontoken token", "token card", "token spell", "spell or token", "commander card", "creature or token",
    "creature with power X or less",  # (X isn't a value)
])
def test_refused_phrases(phrase):
    assert S.parse(phrase) is None


def test_target_phrases():
    # "from a single graveyard": a constraint on the group of targets, not on each card (400.1)
    assert parse_effects("Exile up to two target cards from a single graveyard.") == (
        [{"do": "exile", "who": "target:0"}], [{"what": CARD_IN_GRAVEYARD, "min": 0, "max": 2, "same_graveyard": True}], False)
    assert parse_effects("Exile target card from a single graveyard.") == (  # one target: vacuous
        [{"do": "exile", "who": "target"}], CARD_IN_GRAVEYARD, False)
    assert parse_effects("Exile up to three target cards from graveyards.")[1] == [{"what": CARD_IN_GRAVEYARD, "min": 0, "max": 3}]
    assert language.target_group("one, two, or three target attacking or blocking creatures") == {
        "what": 'sel:{"in_combat":true,"types":["Creature"]}', "min": 1, "max": 3}
    assert parse_effects("Tap target creature defending player controls.")[1] == 'sel:{"controller":"defending","types":["Creature"]}'
    # "another target creature or planeswalker that's black or red" carries its plain selector
    assert parse_effects("Destroy target creature. Destroy another target creature that's green.")[1][1] == {
        "what": 'sel:{"colors":["G"],"types":["Creature"]}', "min": 1, "max": 1, "distinct_from": [0]}


@pytest.mark.parametrize("text", [
    "Tap two target creatures defending player controls.",  # one specific defending player (508.5a): not modelled
    "Creatures defending player controls get -1/-1 until end of turn.",  # not targeted: whose creatures? (508.5)
    "Tap each creature defending player controls.",
    "Exile two target cards from an opponent's graveyard.",  # (unchanged: the same opponent's?)
])
def test_refused_target_phrases(text):
    assert parse_effects(text) is None


# -- matching -------------------------------------------------------------------------------
def test_combat_statuses_and_defending_players(cards):
    """A three-player combat (506.2a, 802): Alice's Axe attacks Carol, her Bow attacks Bob."""
    s = table(cards, players=3)
    axe = creature(s, "p1", "Axe")
    bow = creature(s, "p1", "Bow")
    guard_b = creature(s, "p2", "Guard B")
    guard_c = creature(s, "p3", "Guard C")
    small_c = creature(s, "p3", "Small C", "1/1")
    automate(s)
    act(s, "p1", type="set_prefs", response="on")
    attack(s, (axe, "p3"), (bow, "p2"))
    plan = Plan(s.state, "p1", cards, None)

    def found(phrase, you="p1", source=None):
        return set(S.candidates(plan, S.parse(phrase), you, source))

    assert found("attacking or blocking creature") == {axe.id, bow.id}
    assert found("attacking creature") == {axe.id, bow.id}
    # 508.5: the defending player of an attacking creature's ability is the player it attacks
    assert found("creature defending player controls", source=axe.id) == {guard_c.id, small_c.id}
    assert found("creature defending player controls", source=bow.id) == {guard_b.id}
    # a source that isn't attacking: any player being attacked (508.5a: the chooser picks one)
    assert found("creature defending player controls") == {guard_b.id, guard_c.id, small_c.id}
    assert found("creature that's attacking you", you="p2") == {bow.id}
    assert found("creature that's attacking you", you="p3") == {axe.id}
    assert found("creature that's attacking you", you="p1") == set()
    assert found("1/1 creature") == {small_c.id}
    assert found("creature token", you="p3") == {axe.id, bow.id, guard_b.id, guard_c.id, small_c.id}
    assert found("token you control", you="p3") == {guard_c.id, small_c.id}
    assert found("nontoken creature") == set()
    # blockers: Bob blocks the Bow; then blocking creatures are in combat too (509.1g)
    while decision(s) is None or decision(s).kind != "declare_blockers":
        act(s, s.state.rules.priority, type="pass_priority")
    block(s, "p2", (guard_b, bow))
    block(s, "p3")
    plan = Plan(s.state, "p1", cards, None)
    assert found("blocking creature") == {guard_b.id}
    assert found("attacking or blocking creature") == {axe.id, bow.id, guard_b.id}
    assert found("attacking or blocking creature", you="p2") == {axe.id, bow.id, guard_b.id}
    assert found("creature defending player controls") == {guard_b.id, guard_c.id, small_c.id}


def test_outside_combat_nothing_is_attacking_blocking_or_defending(cards):
    s = build(cards)
    a, b = token(s, "p1", "Ant"), token(s, "p2", "Bee")
    plan = Plan(s.state, "p1", cards, None)
    assert S.candidates(plan, S.parse("attacking or blocking creature"), "p1") == []
    assert S.candidates(plan, S.parse("creature defending player controls"), "p1", source=a.id) == []
    assert S.candidates(plan, S.parse("creature token"), "p1") == [a.id, b.id]


def test_commander_and_other_than_self(cards):
    s = build(cards)
    krenko = named(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    elf = token(s, "p1", "Elf")
    plan = Plan(s.state, "p1", cards, None)
    assert S.candidates(plan, S.parse("commander"), "p1") == [krenko.id]
    assert S.candidates(plan, S.parse("commander you own"), "p2") == []
    assert set(S.candidates(plan, S.parse("creature other than ~"), "p1", source=krenko.id)) == {elf.id}


def test_colors_and_graveyards(cards):
    s = build(cards, "Lightning Bolt")
    bolt, forest = named(s, "Lightning Bolt"), named(s, "Forest")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[bolt.id, forest.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[island.id], to={"zone": "graveyard"})
    plan = Plan(s.state, "p1", cards, None)
    assert set(S.candidates(plan, S.parse("card from a single graveyard"), "p1")) == {bolt.id, forest.id, island.id}
    assert set(S.candidates(plan, S.parse("card from graveyards"), "p2")) == {bolt.id, forest.id, island.id}
    assert S.candidates(plan, S.parse("land card from an opponent's graveyard"), "p1") == [island.id]
    red = token(s, "p1", "Red")  # (a colorless token: no mana cost)
    plan = Plan(s.state, "p1", cards, None)
    assert S.candidates(plan, S.parse("creature that's black or red"), "p1") == []
    assert S.candidates(plan, S.parse("creature that's one or more colors"), "p1") == []
    assert red.id in S.candidates(plan, S.parse("creature"), "p1")


# -- in play ----------------------------------------------------------------------------------
def test_attack_trigger_targets_the_defending_players_creature(cards):
    """"Whenever ~ attacks, tap target creature defending player controls." (Fiend Binder) in a
    three-player game: only the creatures of the player it attacks are offered (508.5)."""
    s = table(cards, players=3)
    binder = creature(s, "p1", "Binder", "2/2", "Whenever this creature attacks, tap target creature defending player controls.")
    bow = creature(s, "p1", "Bow")
    guard_b = creature(s, "p2", "Guard B")
    guard_c = creature(s, "p3", "Guard C")
    automate(s)
    attack(s, (binder, "p3"), (bow, "p2"))
    d = decision(s)
    assert d.player == "p1" and {o.id for o in d.options} == {guard_c.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[guard_c.id])
    pass_until_stack_empty(s)
    assert s.state.cards[guard_c.id].tapped and not s.state.cards[guard_b.id].tapped
    replay_matches(s)


def test_attack_trigger_with_no_creature_of_the_defending_player_is_removed(cards):
    s = table(cards, players=3)
    binder = creature(s, "p1", "Binder", "2/2", "Whenever this creature attacks, tap target creature defending player controls.")
    creature(s, "p2", "Guard B")
    automate(s)
    attack(s, (binder, "p3"))  # Carol has no creatures: 603.3d, no legal target
    pass_until_stack_empty(s)
    assert decision(s) is None or decision(s).kind == "declare_blockers"
    assert not s.state.zones.get("stack")


def test_ability_targeting_an_attacking_or_blocking_creature(cards):
    s = table(cards)
    axe = creature(s, "p1", "Axe")
    idle = creature(s, "p1", "Idle")
    advocate = creature(s, "p1", "Advocate", "1/1", "{1}: Target attacking or blocking creature gets +2/+2 until end of turn.")
    guard = creature(s, "p2", "Guard")
    automate(s)
    act(s, "p1", type="set_prefs", response="on")
    attack(s, (axe, "p2"))
    while decision(s) is None or decision(s).kind != "declare_blockers":
        act(s, s.state.rules.priority, type="pass_priority")
    block(s, "p2", (guard, axe))
    assert s.state.rules.priority == "p1"
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=advocate.id, ability=0, targets=[idle.id])
    act(s, "p1", type="activate_ability", card_id=advocate.id, ability=0, targets=[guard.id])  # the blocker
    pass_until_stack_empty(s)
    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[guard.id]).pt == (4, 4)
    act(s, "p1", type="activate_ability", card_id=advocate.id, ability=0, targets=[axe.id])  # the attacker
    pass_until_stack_empty(s)
    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[axe.id]).pt == (4, 4)
    replay_matches(s)


def test_cards_from_a_single_graveyard(cards):
    """"Exile up to two target cards from a single graveyard." (Famished Ghoul): the targets
    are chosen together and must share a graveyard (400.1); a mix is refused."""
    s = build(cards, "Lightning Bolt")
    bolt, forest = named(s, "Lightning Bolt"), named(s, "Forest")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[bolt.id, forest.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[island.id], to={"zone": "graveyard"})
    ghoul = token(s, "p1", "Ghoul", text="{1}: Exile up to two target cards from a single graveyard.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="single graveyard"):
        act(s, "p1", type="activate_ability", card_id=ghoul.id, ability=0, targets=[forest.id, island.id], target_counts=[2])
    act(s, "p1", type="activate_ability", card_id=ghoul.id, ability=0)
    d = decision(s)
    assert (d.kind, d.min_choices, d.max_choices) == ("choose_cards", 0, 2)
    assert {o.id for o in d.options} == {bolt.id, forest.id, island.id}  # any graveyard …
    with pytest.raises(ActionError, match="single graveyard"):  # … but one of them
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id, island.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id, forest.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p1:exile" and s.state.cards[forest.id].zone == "p1:exile"
    assert island.id in zone(s.state, "p2", "graveyard")
    replay_matches(s)


def test_one_card_from_another_players_graveyard_is_fine(cards):
    s = build(cards)
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"zone": "graveyard"})
    ghoul = token(s, "p1", "Ghoul", text="{1}: Exile up to two target cards from a single graveyard.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=ghoul.id, ability=0, targets=[island.id], target_counts=[1])
    pass_until_stack_empty(s)
    assert s.state.cards[island.id].zone == "p2:exile"
    replay_matches(s)


def test_targets_by_size_token_and_other_than_self(cards):
    s = build(cards)
    small = token(s, "p2", "Small", "1/1")
    big = token(s, "p2", "Big", "2/2")
    aegis = token(s, "p1", "Aegis", text="{1}: Target 1/1 creature gets +1/+2 until end of turn.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=aegis.id, ability=0, targets=[big.id])
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=0, targets=[small.id])
    pass_until_stack_empty(s)
    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[small.id]).pt == (2, 3)
    poplar = token(s, "p1", "Poplar", text="{1}: Target creature other than this creature gets -1/-1 until end of turn.")
    mana(s, C=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=poplar.id, ability=0, targets=[poplar.id])
    act(s, "p1", type="activate_ability", card_id=poplar.id, ability=0, targets=[aegis.id])
    pass_until_stack_empty(s)
    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[aegis.id]).pt == (1, 1)
    hunter = token(s, "p1", "Hunter", text="{1}: Destroy target creature token.")
    krenko = named(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    mana(s, C=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="activate_ability", card_id=hunter.id, ability=0, targets=[krenko.id])
    act(s, "p1", type="activate_ability", card_id=hunter.id, ability=0, targets=[big.id])
    pass_until_stack_empty(s)
    assert big.id not in s.state.cards
    replay_matches(s)
