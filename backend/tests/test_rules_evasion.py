"""Evasion, blocking and untap restrictions as static abilities over the selector grammar
(app/rules/statics.py rules → Characteristics.imposed → app/rules/combat.py, the untap step).

CR 2026-09-25: 509.1b (restrictions: "can't block", evasion abilities, cumulative), 509.1c
(requirements: "must be blocked if able", "blocks each combat if able"), 508.1c-d (attack
restrictions and requirements), 502.3 (permanents an effect keeps from untapping), 506.5
(attacking / blocking alone), 611.3a (a static applies to whatever its text indicates right now),
702.9b flying and 702.111b menace as the model for "can't be blocked except by …".
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, selectors, statics
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.game_helpers import act, turn_on
from tests.test_rules_combat import attack, automate, block, creature, decision, table
from tests.test_rules_effects import replay_matches


def key(phrase):
    return selectors.parse(phrase).key()


def token(s, pid, name, type_line, text="", pt=None):
    tok = {"name": name, "type_line": type_line, "text": text}
    if pt:
        tok["power"], tok["toughness"] = pt.split("/")
    act(s, pid, type="create_token", player=pid, token=tok)
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def imposed(s, cards, card):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id]).imposed


def blocks(s, pid, *pairs):
    """Declare blockers: False when the engine refuses the declaration (the table is unchanged)."""
    try:
        block(s, pid, *pairs)
    except ActionError:
        return False
    return True


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "who", "rules", "extra"), [
    ("~ can't be blocked by creatures with power 2 or less.", "self",
     ["cant_be_blocked_by:" + key("creatures with power 2 or less")], {}),
    ("~ can't be blocked by creatures with power 3 or greater.", "self",
     ["cant_be_blocked_by:" + key("creatures with power 3 or greater")], {}),
    ("~ can't be blocked except by two or more creatures.", "self", ["min_blockers:2"], {}),
    ("~ can't be blocked except by three or more creatures.", "self", ["min_blockers:3"], {}),
    ("~ can't be blocked except by creatures with flying or reach.", "self",
     ["cant_be_blocked_except_by:" + key("creatures with flying") + "|" + key("creatures with reach")], {}),
    ("~ can't be blocked except by creatures with flying.", "self", ["cant_be_blocked_except_by:" + key("creatures with flying")], {}),
    ("~ can't be blocked except by black creatures.", "self", ["cant_be_blocked_except_by:" + key("black creatures")], {}),
    ("~ can't be blocked by artifact creatures.", "self", ["cant_be_blocked_by:" + key("artifact creatures")], {}),
    ("~ can't be blocked by Walls.", "self", ["cant_be_blocked_by:" + key("Walls")], {}),
    ("~ can't be blocked by creatures with flying.", "self", ["cant_be_blocked_by:" + key("creatures with flying")], {}),
    ("~ can't be blocked by more than one creature.", "self", ["max_one_blocker"], {}),
    ("~ can't be blocked by creatures with greater power.", "self", ["cant_be_blocked_by_power:greater"], {}),
    ("Creatures with power less than ~'s power can't block it.", "self", ["cant_be_blocked_by_power:less"], {}),
    ("~ can't be blocked as long as defending player controls an artifact.", "self",
     ["cant_be_blocked_if_defender_controls:" + selectors.parse("artifact").key()], {}),
    ("~ can't be blocked as long as it's attacking alone.", "self", ["cant_be_blocked"],
     {"conditions": [{"static": "self", "test": "attacking_alone"}]}),
    ("~ can't block and can't be blocked.", "self", ["cant_block", "cant_be_blocked"], {}),
    ("~ can't block.", "self", ["cant_block"], {}),
    ("~ can't attack.", "self", ["cant_attack"], {}),
    ("~ can't attack or block.", "self", ["cant_attack_or_block"], {}),
    ("~ can't attack or block alone.", "self", ["cant_attack_alone", "cant_block_alone"], {}),
    ("~ can't attack alone.", "self", ["cant_attack_alone"], {}),
    ("~ can block only creatures with flying.", "self", ["block_only:" + key("creatures with flying")], {}),
    ("~ can't block creatures with power 3 or greater.", "self", ["cant_block_sel:" + key("creatures with power 3 or greater")], {}),
    ("~ can't block creatures with power greater than ~'s power.", "self", ["cant_block_power:greater"], {}),
    ("~ must be blocked if able.", "self", ["must_be_blocked"], {}),
    ("~ blocks each combat if able.", "self", ["must_block"], {}),
    ("~ attacks each combat if able.", "self", ["must_attack"], {}),
    ("~ attacks or blocks each combat if able.", "self", ["must_attack", "must_block"], {}),
    ("~ doesn't untap during your untap step.", "self", ["doesnt_untap"], {}),
    ("~ doesn't untap during your untap step if it has a depletion counter on it.", "self", ["doesnt_untap"],
     {"conditions": [{"static": "self_counter", "counter": "depletion", "op": ">=", "n": 1}]}),
    ("~ attacks each combat if able unless you control another Ally.", "self", ["must_attack"],
     {"conditions": [{"static": "not", "cond": {"value": {"count": key("another Ally you control")}, "op": ">=", "n": 1}}]}),
    ("~ can't attack or block unless you control another creature with power 4 or greater.", "self", ["cant_attack_or_block"],
     {"conditions": [{"static": "not", "cond": {"value": {"count": key("another creature you control with power 4 or greater")},
                                                "op": ">=", "n": 1}}]}),
    ("~ can't block if you control an untapped land.", "self", ["cant_block"],
     {"conditions": [{"value": {"count": key("untapped land you control")}, "op": ">=", "n": 1}]}),
    ("As long as there are seven or more cards in your graveyard, ~ gets +1/+1 and can't block.", "self", ["cant_block"],
     {"p": 1, "t": 1, "conditions": [{"static": "graveyard", "op": ">=", "n": 7}]}),
    # groups (611.3a: whatever matches now, incl. creatures that enter later)
    ("Creatures your opponents control can't block.", key("creatures your opponents control"), ["cant_block"], {}),
    ("Creatures without flying can't attack.", key("creatures without flying"), ["cant_attack"], {}),
    ("Non-Eye creatures you control can't attack.", key("non-Eye creatures you control"), ["cant_attack"], {}),
    ("All creatures attack each combat if able.", key("creatures"), ["must_attack"], {}),
    ("Creatures your opponents control attack each combat if able.", key("creatures your opponents control"), ["must_attack"], {}),
    ("All creatures block each combat if able.", key("creatures"), ["must_block"], {}),
    ("Cowards can't block Warriors.", key("Cowards"), ["cant_block_sel:" + key("Warriors")], {}),
    ("Creatures with flying can block only creatures with flying.", key("creatures with flying"),
     ["block_only:" + key("creatures with flying")], {}),
    ("Each creature you control can't be blocked by more than one creature.", key("creatures you control"), ["max_one_blocker"], {}),
    ("Islands don't untap during their controllers' untap steps.", key("Islands"), ["doesnt_untap"], {}),
    ("Creatures with power 3 or greater don't untap during their controllers' untap steps.",
     key("creatures with power 3 or greater"), ["doesnt_untap"], {}),
    ("Lands don't untap during their controllers' untap steps.", key("lands"), ["doesnt_untap"], {}),
    # Auras and Equipment (303.4b / 301.5a): rules for what they're attached to
    ("Enchanted creature gets +2/+2 and attacks each combat if able.", "attached", ["must_attack"], {"p": 2, "t": 2}),
    ("Enchanted creature gets +1/+1 and can't be blocked.", "attached", ["cant_be_blocked"], {"p": 1, "t": 1}),
    ("Enchanted creature gets -2/-0 and can't block.", "attached", ["cant_block"], {"p": -2}),
    ("Enchanted creature can block only creatures with flying.", "attached", ["block_only:" + key("creatures with flying")], {}),
    ("Equipped creature gets +2/+2 and doesn't untap during its controller's untap step.", "attached", ["doesnt_untap"],
     {"p": 2, "t": 2}),
    ("Enchanted permanent doesn't untap during its controller's untap step and its activated abilities can't be activated.",
     "attached", ["doesnt_untap", "cant_activate"], {}),
])
def test_parse_rules(text, who, rules, extra):
    d = statics.parse(text)
    assert d is not None and d["static"] == "grant" and d["who"] == who
    assert d["rules"] == rules
    expected = {"p": 0, "t": 0, "base": None, "keywords": [], "grants": [], "conditions": [], **extra}
    assert {k: d[k] for k in expected} == expected


@pytest.mark.parametrize("text", [
    "~ can't be blocked by creatures with power 2 or less and/or Walls.",  # two selectors joined oddly
    "~ can't be blocked by creatures with horsemanship.",  # not a selector keyword
    "~ can block an additional creature each combat.",  # one creature blocking two: not on this table yet
    "~ can block any number of creatures.",
    "Enchanted permanent can't attack or block, and its activated abilities can't be activated unless they're mana abilities.",
    "~ can't be blocked as long as you've drawn two or more cards this turn.",  # no such condition
    "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.",
    "~ gets +1/+1 if you control a Forest.",  # "if" belongs to restrictions only
    "No more than one creature can attack each combat.",
    "~ must be blocked by two or more creatures if able.",
    "Creature spells you control can't be countered.",  # spells: not a battlefield selector
    "Players can't gain life.",  # a rule about players, not objects
    "~ can't be blocked by creatures that don't have a name.",
    "~ can't attack a player it has already attacked this turn.",
    "~ enters tapped and doesn't untap during your untap step.",
    "Blue creatures can't block creatures you control.",  # "you" would be lost once the rule sits on a blue creature
    "Enchanted creature can't block creatures you control.",
])
def test_unknown_rules_stay_manual(text):
    assert statics.parse(text) is None


def test_coverage_counts_rule_statics():
    ab = parse_abilities("Flying\nThis creature can't be blocked by creatures with power 2 or less.\n"
                         "Creatures your opponents control can't block.\nThis creature can block an additional creature each combat.")
    feats = coverage.features_of(Characteristics(name="Ghost", types=frozenset({"Creature"}), abilities=tuple(ab)))
    assert [f.supported for f in feats if f.id.startswith("text:")] == [True, True, False]


# -- evasion on the attacker --------------------------------------------------------------
def test_power_threshold_reads_the_blockers_current_power(cards):
    s = table(cards)
    creeper = creature(s, "p1", "Creeper", "3/3", "This creature can't be blocked by creatures with power 2 or less.")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (creeper, "p2"))
    assert decision(s).kind == "declare_blockers"
    with pytest.raises(ActionError, match="power 2 or less"):
        block(s, "p2", (guard, creeper))
    creature(s, "p2", "Banner", "0/4", "Creatures you control get +1/+1.")  # the Guard is 3/3 now (layer 7c)
    block(s, "p2", (guard, creeper))
    assert s.state.players["p2"].life == 40 and guard.id not in s.state.cards  # a 3/3 blocked a 3/3
    replay_matches(s)


def test_power_threshold_greater(cards):
    s = table(cards)
    sneak = creature(s, "p1", "Sneak", "1/1", "This creature can't be blocked by creatures with power 3 or greater.")
    big = creature(s, "p2", "Big", "3/3")
    small = creature(s, "p2", "Small", "2/2")
    automate(s)
    attack(s, (sneak, "p2"))
    assert not blocks(s, "p2", (big, sneak))
    assert blocks(s, "p2", (small, sneak))


def test_relative_power_wordings(cards):
    s = table(cards)
    wolf = creature(s, "p1", "Wolf", "3/3", "Creatures with power less than Wolf's power can't block it.")
    pet = creature(s, "p1", "Pet", "2/2", "This creature can't be blocked by creatures with greater power.")
    weak = creature(s, "p2", "Weak", "2/2")
    strong = creature(s, "p2", "Strong", "3/3")
    automate(s)
    attack(s, (wolf, "p2"), (pet, "p2"))
    assert not blocks(s, "p2", (weak, wolf))
    assert not blocks(s, "p2", (strong, pet))
    assert blocks(s, "p2", (strong, wolf), (weak, pet))


def test_except_by_two_or_more(cards):
    s = table(cards)
    troll = creature(s, "p1", "Troll", "4/4", "This creature can't be blocked except by two or more creatures.")
    cat = creature(s, "p2", "Cat", "2/2")
    dog = creature(s, "p2", "Dog", "2/2")
    automate(s)
    attack(s, (troll, "p2"))
    with pytest.raises(ActionError, match="2 or more creatures"):
        block(s, "p2", (cat, troll))
    block(s, "p2", (cat, troll), (dog, troll))
    assert troll.id not in s.state.cards  # 2 + 2 damage on a 4/4


def test_except_by_three_or_more_and_menace_share_the_rule(cards):
    s = table(cards)
    troll = creature(s, "p1", "Troll", "4/4", "Menace\nThis creature can't be blocked except by three or more creatures.")
    cat = creature(s, "p2", "Cat", "2/2")
    dog = creature(s, "p2", "Dog", "2/2")
    ox = creature(s, "p2", "Ox", "2/2")
    automate(s)
    attack(s, (troll, "p2"))
    assert not blocks(s, "p2", (cat, troll), (dog, troll))  # the stricter of the two (509.1b: cumulative)
    assert blocks(s, "p2", (cat, troll), (dog, troll), (ox, troll))


def test_except_by_creatures_with_flying_or_reach(cards):
    s = table(cards)
    pest = creature(s, "p1", "Pest", "1/1", "This creature can't be blocked except by creatures with flying or reach.")
    cat = creature(s, "p2", "Cat", "2/2")
    spider = creature(s, "p2", "Spider", "1/3", "Reach")
    automate(s)
    attack(s, (pest, "p2"))
    with pytest.raises(ActionError, match="except by creatures with flying or creatures with reach"):
        block(s, "p2", (cat, pest))
    block(s, "p2", (spider, pest))
    assert pest.id not in s.state.cards


def test_flying_still_reads_as_the_same_rule(cards):
    s = table(cards)
    bird = creature(s, "p1", "Bird", "1/1", "Flying")
    cat = creature(s, "p2", "Cat", "2/2")
    automate(s)
    attack(s, (bird, "p2"))
    with pytest.raises(ActionError, match="flying"):
        block(s, "p2", (cat, bird))


@pytest.mark.parametrize(("text", "type_line", "can_block"), [
    ("This creature can't be blocked by artifact creatures.", "Token Artifact Creature — Golem", False),
    ("This creature can't be blocked by artifact creatures.", "Token Creature — Golem", True),
    ("This creature can't be blocked by Walls.", "Token Creature — Wall", False),
    ("This creature can't be blocked by Walls.", "Token Creature — Bear", True),
    ("This creature can't be blocked except by black creatures.", "Token Creature — Bear", False),
])
def test_cant_be_blocked_by_selector(cards, text, type_line, can_block):
    s = table(cards)
    sneak = creature(s, "p1", "Sneak", "2/2", text)
    guard = token(s, "p2", "Guard", type_line, pt="2/2")
    automate(s)
    attack(s, (sneak, "p2"))
    assert blocks(s, "p2", (guard, sneak)) is can_block


def test_cant_be_blocked_except_by_black_creatures_accepts_one(cards):
    s = table(cards)
    sneak = creature(s, "p1", "Sneak", "2/2", "This creature can't be blocked except by black creatures.")
    act(s, "p2", type="create_token", player="p2", token={"name": "Rat", "type_line": "Token Creature — Rat", "power": "1",
                                                         "toughness": "1", "text": "", "colors": ["B"]})
    rat = next(c for c in s.state.cards.values() if c.name == "Rat")
    automate(s)
    attack(s, (sneak, "p2"))
    assert blocks(s, "p2", (rat, sneak))


def test_cant_be_blocked_while_attacking_alone(cards):
    s = table(cards)
    prowler = creature(s, "p1", "Prowler", "2/2", "This creature can't be blocked as long as it's attacking alone.")
    other = creature(s, "p1", "Other", "2/2")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (prowler, "p2"))
    assert not blocks(s, "p2", (guard, prowler))
    block(s, "p2")
    # next turn of Alice's: with two attackers it can be blocked
    _to_next_turn_of(s, "p1")
    attack(s, (prowler, "p2"), (other, "p2"))
    assert blocks(s, "p2", (guard, prowler))


def test_cant_be_blocked_while_defender_controls_an_artifact(cards):
    s = table(cards)
    beeble = creature(s, "p1", "Beeble", "2/2", "This creature can't be blocked as long as defending player controls an artifact.")
    guard = creature(s, "p2", "Guard", "2/2")
    relic = token(s, "p2", "Relic", "Token Artifact")
    automate(s)
    attack(s, (beeble, "p2"))
    assert not blocks(s, "p2", (guard, beeble))
    act(s, "p2", type="move", card_ids=[relic.id], to={"zone": "graveyard"})
    assert blocks(s, "p2", (guard, beeble))


# -- restrictions on the blocker ----------------------------------------------------------
def test_blocker_restrictions_over_selectors(cards):
    s = table(cards)
    giant = creature(s, "p1", "Giant", "4/4")
    imp = creature(s, "p1", "Imp", "1/1", "Flying")
    mutant = creature(s, "p2", "Mutant", "5/3", "Reach\nThis creature can't block creatures with power 3 or greater.")
    bladder = creature(s, "p2", "Bladder", "1/1", "Reach\nThis creature can block only creatures with flying.")
    canopy = creature(s, "p2", "Owl", "1/1", "Flying")
    token(s, "p2", "Canopy", "Token Enchantment", "Creatures with flying can block only creatures with flying.")
    automate(s)
    attack(s, (giant, "p2"), (imp, "p2"))
    assert not blocks(s, "p2", (mutant, giant))
    assert not blocks(s, "p2", (bladder, giant))
    assert not blocks(s, "p2", (canopy, giant))  # the Canopy's rule on all flyers
    assert blocks(s, "p2", (mutant, imp), (bladder, imp), (canopy, imp))


def test_cowards_cant_block_warriors(cards):
    s = table(cards)
    warrior = token(s, "p1", "Warrior", "Token Creature — Human Warrior", pt="2/2")
    wizard = token(s, "p1", "Wizard", "Token Creature — Human Wizard", pt="2/2")
    coward = token(s, "p2", "Coward", "Token Creature — Human Coward", pt="2/2")
    token(s, "p1", "Intimidator", "Token Enchantment", "Cowards can't block Warriors.")
    automate(s)
    attack(s, (warrior, "p2"), (wizard, "p2"))
    assert not blocks(s, "p2", (coward, warrior))
    assert blocks(s, "p2", (coward, wizard))


# -- group restrictions: the source leaving, a creature entering later ------------------------
def test_opponents_creatures_cant_block_source_leaves_and_later_arrivals(cards):
    s = table(cards)
    axe = creature(s, "p1", "Axe", "2/2")
    early = creature(s, "p2", "Early", "2/2")
    curse = token(s, "p1", "Curse", "Token Enchantment", "Creatures your opponents control can't block.")
    turn_on(s)
    late = creature(s, "p2", "Late", "2/2")  # entered after the static: still affected (611.3a)
    assert "cant_block" in imposed(s, cards, early) and "cant_block" in imposed(s, cards, late)
    assert "cant_block" not in imposed(s, cards, axe)  # Alice's own creature isn't an opponent's
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    attack(s, (axe, "p2"))
    assert not blocks(s, "p2", (early, axe))
    assert not blocks(s, "p2", (late, axe))
    act(s, "p1", type="move", card_ids=[curse.id], to={"zone": "graveyard"})  # 611.3b: gone with its source
    assert "cant_block" not in imposed(s, cards, late)
    assert blocks(s, "p2", (late, axe))
    replay_matches(s)


def test_multiplayer_opponents_cant_block_is_from_the_controllers_view(cards):
    s = table(cards, players=3)
    token(s, "p1", "Curse", "Token Enchantment", "Creatures your opponents control can't block.")
    alice = creature(s, "p1", "Alice's Guard", "2/2")
    bob_a = creature(s, "p2", "Bob's Axe", "2/2")
    bob_b = creature(s, "p2", "Bob's Bow", "2/2")
    carol = creature(s, "p3", "Carol's Guard", "2/2")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    _to_next_turn_of(s, "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bob_a.id, "target": "p3"}, {"card_id": bob_b.id, "target": "p1"}])
    assert decision(s).player == "p3"
    assert not blocks(s, "p3", (carol, bob_a))  # Carol is Alice's opponent: she can't block anyone
    block(s, "p3")
    assert decision(s).player == "p1"
    assert blocks(s, "p1", (alice, bob_b))  # Alice's own creatures may block
    assert s.state.players["p3"].life == 38 and s.state.players["p1"].life == 40


def test_conditional_restriction_unless_you_control(cards):
    s = table(cards)
    god = creature(s, "p1", "God", "5/5", "This creature can't attack or block unless you control another creature with power 4 or greater.")
    bear = creature(s, "p1", "Bear", "2/2")
    automate(s)
    assert {o.id for o in decision(s).options} == {f"a:{bear.id}", "t:p2"}
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, (god, "p2"))
    act(s, "p1", type="declare_attackers", attackers=[])
    creature(s, "p1", "Giant", "4/4")
    assert "cant_attack_or_block" not in imposed(s, cards, god)
    _to_next_turn_of(s, "p1")
    assert f"a:{god.id}" in {o.id for o in decision(s).options}


# -- requirements (509.1c, 508.1d) and "alone" (506.5) -------------------------------------------
def test_must_be_blocked_if_able(cards):
    s = table(cards)
    soldier = creature(s, "p1", "Soldier", "2/2", "This creature must be blocked if able.")
    other = creature(s, "p1", "Other", "2/2")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (soldier, "p2"), (other, "p2"))
    with pytest.raises(ActionError, match="must be blocked if able"):
        block(s, "p2")
    with pytest.raises(ActionError, match="must be blocked if able"):
        block(s, "p2", (guard, other))  # the Guard could block the Soldier instead
    block(s, "p2", (guard, soldier))
    assert s.state.players["p2"].life == 38


def test_must_be_blocked_needs_no_block_when_nothing_can(cards):
    s = table(cards)
    soldier = creature(s, "p1", "Soldier", "2/2", "Flying\nThis creature must be blocked if able.")
    creature(s, "p2", "Guard", "2/2")  # no flying or reach
    automate(s)
    attack(s, (soldier, "p2"))
    block(s, "p2")
    assert s.state.players["p2"].life == 38


def test_blocks_each_combat_if_able(cards):
    s = table(cards)
    axe = creature(s, "p1", "Axe", "2/2")
    screen = creature(s, "p2", "Screen", "1/3", "This creature blocks each combat if able.")
    automate(s)
    attack(s, (axe, "p2"))
    with pytest.raises(ActionError, match="blocks each combat if able"):
        block(s, "p2")
    block(s, "p2", (screen, axe))
    assert s.state.players["p2"].life == 40


def test_group_attack_requirement_and_restriction(cards):
    s = table(cards)
    turtle = creature(s, "p1", "Turtle", "2/2")
    creature(s, "p1", "Hawk", "1/1", "Flying")
    token(s, "p1", "Lure", "Token Enchantment", "Creatures your opponents control attack each combat if able.")
    token(s, "p2", "Moat", "Token Enchantment", "Creatures without flying can't attack.")
    bob_bird = creature(s, "p2", "Bob's Bird", "1/1", "Flying")
    bob_bear = creature(s, "p2", "Bob's Bear", "2/2")
    automate(s)
    with pytest.raises(ActionError, match="can't attack"):
        attack(s, (turtle, "p2"))  # the Moat (a static of Bob's) stops Alice's ground creature too
    act(s, "p1", type="declare_attackers", attackers=[])
    _to_next_turn_of(s, "p2")
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])  # the Bird must attack (the Bear can't)
    assert f"a:{bob_bear.id}" not in {o.id for o in decision(s).options}
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bob_bird.id, "target": "p1"}])


def test_cant_attack_alone_and_cant_block_alone(cards):
    s = table(cards)
    pegasus = creature(s, "p1", "Pegasus", "2/2", "This creature can't attack or block alone.")
    other = creature(s, "p1", "Other", "2/2")
    brawler = creature(s, "p2", "Brawler", "2/2", "This creature can't block alone.")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    with pytest.raises(ActionError, match="can't attack alone"):
        attack(s, (pegasus, "p2"))
    attack(s, (pegasus, "p2"), (other, "p2"))
    assert not blocks(s, "p2", (brawler, pegasus))
    assert blocks(s, "p2", (brawler, pegasus), (guard, other))


# -- the untap step (502.3) ---------------------------------------------------------------------
def _to_next_turn_of(s, pid):
    """Pass (attacking with nothing) until it's ``pid``'s declare attackers step."""
    for _ in range(60):
        d = decision(s)
        if d is not None and d.kind == "declare_attackers":
            if d.player == pid:
                return
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached that turn")


def test_dont_untap_applies_to_the_selector_only(cards):
    s = table(cards)
    big = creature(s, "p1", "Big", "4/4")
    small = creature(s, "p1", "Small", "2/2")
    token(s, "p2", "Meekstone", "Token Artifact", "Creatures with power 3 or greater don't untap during their controllers' untap steps.")
    automate(s)
    attack(s, (big, "p2"), (small, "p2"))  # both tap
    assert s.state.cards[big.id].tapped and s.state.cards[small.id].tapped
    assert "doesnt_untap" in imposed(s, cards, big) and "doesnt_untap" not in imposed(s, cards, small)
    _to_next_turn_of(s, "p1")
    assert s.state.turn.number == 3
    assert s.state.cards[big.id].tapped  # 502.3: kept from untapping
    assert not s.state.cards[small.id].tapped
    replay_matches(s)


def test_dont_untap_reads_current_power(cards):
    s = table(cards)
    grown = creature(s, "p1", "Grown", "2/2")
    creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    token(s, "p2", "Meekstone", "Token Artifact", "Creatures with power 3 or greater don't untap during their controllers' untap steps.")
    automate(s)
    attack(s, (grown, "p2"))
    _to_next_turn_of(s, "p1")
    assert s.state.cards[grown.id].tapped  # a 2/2 with +1/+1 has power 3 (layer 7c before the rule is read)


def test_islands_dont_untap(cards):
    s = table(cards)
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    island = token(s, "p1", "Island", "Token Land — Island")
    token(s, "p2", "Choke", "Token Enchantment", "Islands don't untap during their controllers' untap steps.")
    act(s, "p1", type="tap", card_ids=[forest.id, island.id], tapped=True)
    creature(s, "p1", "Bear", "2/2")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    _to_next_turn_of(s, "p1")
    assert s.state.cards[island.id].tapped and not s.state.cards[forest.id].tapped
