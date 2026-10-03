"""Static grants on the selector grammar (app/rules/statics.py) applied in layer order
(app/rules/layers.py): CR 604.2, 611.3a-b, 613.1f, 613.4b-c, 613.7."""

from __future__ import annotations

import pytest

from app.game.rules_state import ContinuousEffect
from app.rules import coverage, selectors, statics
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from app.rules.plan import Plan
from tests.game_helpers import act, turn_on
from tests.test_rules_anthems import goblin
from tests.test_rules_combat import creature, table
from tests.test_rules_effects import replay_matches


def key(phrase):
    return selectors.parse(phrase).key()


def ch(s, cards, card):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id])


def token(s, pid, name, type_line, text="", pt=None):
    tok = {"name": name, "type_line": type_line, "text": text}
    if pt:
        tok["power"], tok["toughness"] = pt.split("/")
    act(s, pid, type="create_token", player=pid, token=tok)
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "who", "parts"), [
    ("Creatures you control get +1/+1.", key("creatures you control"), {"p": 1, "t": 1}),
    ("Other Elves you control get +1/+1 and have haste.", key("other Elves you control"),
     {"p": 1, "t": 1, "keywords": ["haste"]}),
    ("Other green creatures you control get +1/+1.", key("other green creatures you control"), {"p": 1, "t": 1}),
    ("All Slivers have flying.", key("Slivers"), {"keywords": ["flying"]}),
    ("Each creature you control with a +1/+1 counter on it has trample.",
     key("creature you control with a +1/+1 counter on it"), {"keywords": ["trample"]}),
    ("Creature tokens you control get +1/+1.", key("token creatures you control"), {"p": 1, "t": 1}),
    ("Attacking creatures you control have double strike.", key("attacking creatures you control"),
     {"keywords": ["double strike"]}),
    ("Other permanents you control have hexproof.", key("other permanents you control"), {"keywords": ["hexproof"]}),
    ("Creatures your opponents control get -1/-1.", key("creatures your opponents control"), {"p": -1, "t": -1}),
    ("Nonwhite creatures get -1/-1.", key("nonwhite creatures"), {"p": -1, "t": -1}),
    ("Creatures with flying get +2/+0.", key("creatures with flying"), {"p": 2}),
    ('Lands you control have "{T}: Add {G}."', key("lands you control"), {"grants": ["{T}: Add {G}."]}),
    ('Commander creatures you own have "{T}: Add {G}."', key("commander creatures you own"),
     {"grants": ["{T}: Add {G}."]}),
    ("Other creatures have base power and toughness 2/2.", key("other creatures"), {"base": [2, 2]}),
    ("Enchanted creature gets +2/+2 and has first strike.", "attached", {"p": 2, "t": 2, "keywords": ["first strike"]}),
    ("Equipped creature gets +1/+1.", "attached", {"p": 1, "t": 1}),
    ("Enchanted creature has flying and vigilance.", "attached", {"keywords": ["flying", "vigilance"]}),
    ('Enchanted creature gets +2/+2 and has "{T}: Add {G}."', "attached", {"p": 2, "t": 2, "grants": ["{T}: Add {G}."]}),
    ("~ gets +2/+2 as long as you control three or more artifacts.", "self",
     {"p": 2, "t": 2, "conditions": [{"value": {"count": key("artifacts you control")}, "op": ">=", "n": 3}]}),
    ("During your turn, ~ has first strike.", "self", {"keywords": ["first strike"], "conditions": [{"static": "your_turn"}]}),
    ("As long as ~ is equipped, it gets +1/+1 and has flying.", "self",
     {"p": 1, "t": 1, "keywords": ["flying"], "conditions": [{"static": "self", "test": "equipped"}]}),
    ("~ has hexproof as long as it's untapped.", "self",
     {"keywords": ["hexproof"], "conditions": [{"static": "self", "test": "untapped"}]}),
    ("~ has indestructible as long as it has a divinity counter on it.", "self",
     {"keywords": ["indestructible"], "conditions": [{"static": "self_counter", "counter": "divinity", "op": ">=", "n": 1}]}),
    ("As long as there are seven or more cards in your graveyard, ~ gets +1/+1 and has flying.", "self",
     {"p": 1, "t": 1, "keywords": ["flying"], "conditions": [{"static": "graveyard", "op": ">=", "n": 7}]}),
    ("Artifacts you control have shroud as long as you control three or more artifacts.", key("artifacts you control"),
     {"keywords": ["shroud"], "conditions": [{"value": {"count": key("artifacts you control")}, "op": ">=", "n": 3}]}),
    ("During your turn, creatures you control get +2/+0.", key("creatures you control"),
     {"p": 2, "conditions": [{"static": "your_turn"}]}),
])
def test_parse(text, who, parts):
    d = statics.parse(text)
    assert d is not None and d["kind"] == "static" and d["static"] == "grant" and d["who"] == who
    expected = {"p": 0, "t": 0, "base": None, "keywords": [], "grants": [], "conditions": [], **parts}
    assert {k: d[k] for k in expected} == expected


@pytest.mark.parametrize("text", [
    "Creatures you control get +1/+1 until end of turn.",  # a duration: an effect, not a static
    "Enchanted creature gets +1/+1 and has protection from the chosen color.",  # a quality chosen as it entered (wave 4L reads the rest)
    "Other creatures you control have cascade.",  # a keyword of spells (wave 6E reads granted exalted)
    "You have hexproof.",  # a player's characteristic (613.10): not modelled
    "Instant and sorcery spells you control have lifelink.",  # spells, not permanents
    "Creatures you control get +1/+1. As long as you have the city's blessing, they also have vigilance.",
    "Enchanted creature gets +1/+2 as long as it's white. Otherwise, it gets -2/-1.",
    "Other creatures have base power and toughness 2/2 and are Bears in addition to their other types.",
    "Creatures enchanted player controls lose all abilities and have base power and toughness 1/1.",
    "Creature you control gets +1/+1.",  # not Oracle wording
    "~ has flying.",  # unconditional self grant: that's a keyword line
    "Each creature you control has trample as long as it's attacking.",  # "it" would be each creature, not the source
    'Enchanted creature has "Whenever ~ attacks, you may draw a card for each foo."',  # an ability the engine can't run
    "As long as an opponent has 10 or less life, ~ gets +2/+1 and has annihilator 2.",  # (wave 4B reads the condition)
    "Creature spells you cast have convoke.",
])
def test_unknown_wordings_stay_manual(text):
    assert statics.parse(text) is None


def test_coverage_counts_static_grants():
    ab = parse_abilities("Other Elves you control get +1/+1 and have haste.\nCreatures you control have vigilance "
                         "as long as you control a Forest.\nYou have hexproof from blue.")  # (wave 5E: "You have hexproof." is read now)
    feats = coverage.features_of(Characteristics(name="Lord", types=frozenset({"Creature"}), abilities=tuple(ab)))
    assert [f.supported for f in feats if f.id.startswith("text:")] == [True, True, False]


# -- the table ------------------------------------------------------------------------------
def test_source_enters_and_leaves_and_later_arrivals_are_affected(cards):
    s = table(cards)
    early = goblin(s, "p1", "Early")
    lord = goblin(s, "p1", "Lord", "2/2", "Other Goblins you control get +1/+1 and have haste.")
    turn_on(s)
    late = goblin(s, "p1", "Late")  # 611.3a: whatever the text indicates, at any moment
    assert ch(s, cards, early).pt == (2, 2) and ch(s, cards, late).pt == (2, 2)
    assert "haste" in ch(s, cards, late).keywords
    assert ch(s, cards, lord).pt == (2, 2) and "haste" not in ch(s, cards, lord).keywords  # "Other"
    act(s, "p1", type="move", card_ids=[lord.id], to={"zone": "graveyard"})  # 611.3b: gone with its source
    assert ch(s, cards, early).pt == (1, 1) and ch(s, cards, late).pt == (1, 1)
    goblin(s, "p1", "Lord 2", "2/2", "Other Goblins you control get +1/+1 and have haste.")  # a new source
    assert ch(s, cards, late).pt == (2, 2)
    replay_matches(s)


def test_you_control_follows_the_sources_controller(cards):
    s = table(cards)
    banner = creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    mine = creature(s, "p1", "Mine", "2/2")
    theirs = creature(s, "p2", "Theirs", "2/2")
    turn_on(s)
    assert ch(s, cards, mine).pt == (3, 3) and ch(s, cards, theirs).pt == (2, 2)
    act(s, "p2", type="set_controller", card_ids=[banner.id], player="p2")
    assert ch(s, cards, mine).pt == (2, 2) and ch(s, cards, theirs).pt == (3, 3)
    assert ch(s, cards, banner).pt == (1, 5)  # the source is one of "creatures you control" too
    replay_matches(s)


def test_anthems_stack_with_counters_and_base_setting_applies_first(cards):
    s = table(cards)
    creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    creature(s, "p1", "Flag", "0/4", "Creatures you control get +2/+0.")
    bear = creature(s, "p1", "Bear", "5/5")
    turn_on(s)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    assert ch(s, cards, bear).pt == (5 + 1 + 2 + 2, 5 + 1 + 2)  # 613.4c: modifications and counters add up
    # 613.4b: a "base power and toughness" static applies in 7b, before every 7c modification
    leveler = creature(s, "p1", "Leveler", "1/1", "Other creatures have base power and toughness 2/2.")
    assert ch(s, cards, bear).pt == (2 + 1 + 2 + 2, 2 + 1 + 2)
    assert ch(s, cards, leveler).pt == (1 + 1 + 2, 1 + 1)  # "Other": its own base stays printed
    act(s, "p1", type="counter", card_ids=[bear.id], kind="-1/-1", delta=1)
    assert ch(s, cards, bear).pt == (6, 4)
    replay_matches(s)


def test_keyword_grant_and_a_later_removal(cards):
    s = table(cards)
    creature(s, "p1", "Wings", "0/4", "Creatures you control have flying.")
    bear = creature(s, "p1", "Bear", "2/2")
    turn_on(s)
    assert "flying" in ch(s, cards, bear).keywords
    r = s.state.rules  # a resolved "loses flying until end of turn" on the Bear: layer 6, a later timestamp
    r.timestamp += 1
    r.effects.append(ContinuousEffect(id="e-test", affected=[r.object_id(bear.id)], layer="6", controller="p1",
                                      remove_keywords=["flying"], timestamp=r.timestamp))
    assert "flying" not in ch(s, cards, bear).keywords
    assert "flying" not in ch(s, cards, bear).granted and "flying" in ch(s, cards, bear).lost


def test_conditional_on_what_you_control(cards):
    s = table(cards)
    golem = creature(s, "p1", "Golem", "2/2", "~ gets +2/+2 as long as you control three or more artifacts.")
    turn_on(s)
    assert ch(s, cards, golem).pt == (2, 2)
    for i in range(3):
        token(s, "p1", f"Cog{i}", "Token Artifact")
    assert ch(s, cards, golem).pt == (4, 4)
    act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Cog0")],
        to={"zone": "graveyard"})
    assert ch(s, cards, golem).pt == (2, 2)  # 611.3a: checked whenever it's looked at
    replay_matches(s)


def test_during_your_turn(cards):
    s = table(cards)
    mine = creature(s, "p1", "Duelist", "2/2", "During your turn, ~ has first strike.")
    theirs = creature(s, "p2", "Duelist", "2/2", "During your turn, ~ has first strike.")
    turn_on(s)
    assert s.state.turn.active_player == "p1"
    assert "first strike" in ch(s, cards, mine).keywords and "first strike" not in ch(s, cards, theirs).keywords


def test_self_conditions_equipped_untapped_and_counters(cards):
    s = table(cards)
    knight = creature(s, "p1", "Knight", "2/2", "As long as ~ is equipped, it gets +1/+1 and has flying.\n"
                                                "~ has hexproof as long as it's untapped.\n"
                                                "~ has indestructible as long as it has a divinity counter on it.")
    sword = token(s, "p1", "Sword", "Token Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {1}")
    turn_on(s)
    now = ch(s, cards, knight)
    assert now.pt == (2, 2) and "hexproof" in now.keywords and not {"flying", "indestructible"} & now.keywords
    act(s, "p1", type="attach", card_ids=[sword.id], to=knight.id)
    assert ch(s, cards, knight).pt == (2 + 1 + 2, 2 + 1) and "flying" in ch(s, cards, knight).keywords
    act(s, "p1", type="tap", card_ids=[knight.id], tapped=True)
    assert "hexproof" not in ch(s, cards, knight).keywords
    act(s, "p1", type="counter", card_ids=[knight.id], kind="divinity", delta=1)
    assert "indestructible" in ch(s, cards, knight).keywords
    other = creature(s, "p1", "Other", "1/1")
    act(s, "p1", type="attach", card_ids=[sword.id], to=other.id)  # the Equipment moves: so does its grant
    assert ch(s, cards, other).pt == (3, 1) and ch(s, cards, knight).pt == (2, 2)
    replay_matches(s)


def test_granted_ability_and_threshold(cards):
    s = table(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    creature(s, "p1", "Druid", "1/1", 'Lands you control have "{T}: Add {C}."')
    thresh = creature(s, "p1", "Werebear", "1/1", "As long as there are seven or more cards in your graveyard, "
                                                  "~ gets +3/+3 and has trample.")
    turn_on(s)
    granted = [a for a in ch(s, cards, forest).abilities if a.index >= 100]
    assert [a.text for a in granted] == ["{T}: Add {C}."] and granted[0].kind == "mana"
    assert ch(s, cards, thresh).pt == (1, 1)
    library = list(s.state.zones["p1:library"])[:7]
    act(s, "p1", type="move", card_ids=library, to={"zone": "graveyard"})
    assert ch(s, cards, thresh).pt == (4, 4) and "trample" in ch(s, cards, thresh).keywords


def test_manual_source_and_face_down_source_do_nothing(cards):
    s = table(cards)
    lord = goblin(s, "p1", "Lord", "2/2", "Other Goblins you control get +1/+1.")
    grunt = goblin(s, "p1", "Grunt")
    turn_on(s)
    assert ch(s, cards, grunt).pt == (2, 2)
    act(s, "p1", type="face_down", card_ids=[lord.id], face_down=True)
    assert ch(s, cards, grunt).pt == (1, 1)  # 708.2: a face-down permanent has no abilities


def test_layer_7_subject_sees_layer_6_grants(cards):
    """613.8: "Creatures with flying get +1/+1" depends on an Aura's "Enchanted creature has flying"
    (layer 6 is applied before the layer-7 effect reads its subject)."""
    s = table(cards)
    creature(s, "p1", "Aviary", "0/1", "Creatures with flying get +1/+1.")
    bear = creature(s, "p1", "Bear", "2/2")
    wings = token(s, "p1", "Wings", "Token Enchantment — Aura", "Enchanted creature has flying.\nEnchant creature")
    act(s, "p1", type="attach", card_ids=[wings.id], to=bear.id)  # (704.5m: an unattached Aura would go)
    turn_on(s)
    assert "flying" in ch(s, cards, bear).keywords and ch(s, cards, bear).pt == (3, 3)
    act(s, "p1", type="move", card_ids=[wings.id], to={"zone": "graveyard"})
    assert "flying" not in ch(s, cards, bear).keywords and ch(s, cards, bear).pt == (2, 2)


def test_conditions_that_count_the_table_with_other_statics_around(cards):
    s = table(cards)
    rider = creature(s, "p1", "Rider", "2/2", "As long as you control a Dragon, ~ has flying.")
    creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    creature(s, "p1", "Lord", "2/2", "Other creatures you control have base power and toughness 2/2.")
    turn_on(s)
    assert "flying" not in ch(s, cards, rider).keywords and ch(s, cards, rider).pt == (3, 3)
    dragon = token(s, "p1", "Wyrm", "Token Creature — Dragon", pt="4/4")
    assert "flying" in ch(s, cards, rider).keywords and ch(s, cards, dragon).pt == (3, 3)
    act(s, "p2", type="set_controller", card_ids=[dragon.id], player="p2")
    assert "flying" not in ch(s, cards, rider).keywords and ch(s, cards, dragon).pt == (4, 4)
    replay_matches(s)


# -- review findings: dependency, granted statics, timestamps, performance -------------------------
def test_dependent_keyword_grant_on_a_static_keyword(cards):
    """613.8: Kwende + Knighthood — the double strike static depends on the first strike static."""
    s = table(cards)
    creature(s, "p1", "Knighthood", "0/1", "Creatures you control have first strike.")
    creature(s, "p1", "Kwende", "2/2", "Creatures you control with first strike have double strike.")
    bear = creature(s, "p1", "Bear", "2/2")
    turn_on(s)
    assert {"first strike", "double strike"} <= ch(s, cards, bear).keywords


def test_dependent_ability_grant_on_a_static_keyword(cards):
    """613.8: Frondland Felidar + Serra's Blessing — a granted ability on "creatures with vigilance"."""
    s = table(cards)
    creature(s, "p1", "Blessing", "0/1", "Creatures you control have vigilance.")
    creature(s, "p1", "Felidar", "3/5", 'Creatures you control with vigilance have "{1}, {T}: Tap target creature."')
    bear = creature(s, "p1", "Bear", "2/2")
    turn_on(s)
    now = ch(s, cards, bear)
    assert "vigilance" in now.keywords
    assert [a.text for a in now.abilities if a.index >= 100] == ["{1}, {T}: Tap target creature."]


def test_granted_static_is_applied(cards):
    """A static another static grants (Inspiring Leader) works on whatever holds it, while the
    granting static applies to that holder."""
    s = table(cards)
    leader = creature(s, "p1", "Leader", "2/2", 'Creatures you control have "Creature tokens you control get +2/+2."')
    tok = creature(s, "p1", "Tok", "1/1")
    turn_on(s)
    now = ch(s, cards, tok)
    assert [a.text for a in now.abilities if a.index >= 100] == ["Creature tokens you control get +2/+2."]
    # every creature Alice controls has the ability, and each one's is its own effect: the Leader's
    # copy and the Tok's own copy both apply to the Tok (both are creature tokens here)
    assert now.pt == (5, 5) and ch(s, cards, leader).pt == (6, 6)
    act(s, "p2", type="set_controller", card_ids=[tok.id], player="p2")  # the Leader's grant no longer reaches it
    assert ch(s, cards, tok).pt == (1, 1) and not [a for a in ch(s, cards, tok).abilities if a.index >= 100]
    act(s, "p1", type="move", card_ids=[leader.id], to={"zone": "graveyard"})
    assert ch(s, cards, tok).pt == (1, 1)
    replay_matches(s)


def test_granted_enters_trigger_fires(cards):
    """An ability a static grants is a real ability of the object: a granted "When this creature
    enters" triggers as it enters (611.3c: the grant applies as the permanent enters)."""
    from tests.test_rules_effects import build, draw_all, hand, mana, pass_until_stack_empty

    s = build(cards)
    draw_all(s)
    token(s, "p1", "Leader", "Token Creature — Human",
          'Creatures you control have "When this creature enters, you gain 1 life."', pt="2/2")
    viper = hand(s, "p1", "Ambush Viper")
    mana(s, G=2)
    life = s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=viper.id)
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].zone == "p1:battlefield" and s.state.players["p1"].life == life + 1


def test_static_grant_after_a_resolved_loss(cards):
    """613.7: "loses flying" resolved first, then Levitation enters (a later timestamp): flying."""
    from app.rules import layers

    s = table(cards)
    bird = creature(s, "p1", "Bird", "1/1", "Flying")
    turn_on(s)
    plan = Plan(s.state, "p1", cards, None)
    layers.add_effect(plan, affected=[plan.oid(s.state.cards[bird.id])], layer="6", source=None, controller="p1",
                      remove_keywords=("flying",), label="loses flying")
    s.state.rules.effects = plan.state.rules.effects
    assert "flying" not in ch(s, cards, bird).keywords
    creature(s, "p1", "Levitation", "0/1", "Creatures you control have flying.")
    assert "flying" in ch(s, cards, bird).keywords
    # and the other way round: the static's source there first, the loss resolved later, wins
    plan = Plan(s.state, "p1", cards, None)
    layers.add_effect(plan, affected=[plan.oid(s.state.cards[bird.id])], layer="6", source=None, controller="p1",
                      remove_keywords=("flying",), label="loses flying")
    s.state.rules.effects = plan.state.rules.effects
    assert "flying" not in ch(s, cards, bird).keywords


def test_two_base_setters_timestamp_order(cards):
    """613.7d: of two "base power and toughness" statics, the one whose source entered later wins."""
    s = table(cards)
    bear = creature(s, "p1", "Bear", "5/5")
    godhead = creature(s, "p1", "Godhead", "0/1", "Other creatures have base power and toughness 1/1.")
    creature(s, "p1", "Archon", "0/1", "Other creatures have base power and toughness 3/3.")
    turn_on(s)
    assert ch(s, cards, bear).pt == (3, 3)
    act(s, "p1", type="move", card_ids=[godhead.id], to={"zone": "graveyard"})  # (a token: it's gone)
    creature(s, "p1", "Godhead", "0/1", "Other creatures have base power and toughness 1/1.")  # a new object: later
    assert ch(s, cards, bear).pt == (1, 1)
    replay_matches(s)


def test_static_base_after_a_resolved_set(cards):
    """613.7: "becomes 0/1 until end of turn" resolved, then Godhead of Awe enters: 1/1."""
    from app.rules import layers

    s = table(cards)
    bear = creature(s, "p1", "Bear", "5/5")
    turn_on(s)
    plan = Plan(s.state, "p1", cards, None)
    layers.add_effect(plan, affected=[plan.oid(s.state.cards[bear.id])], layer="7b", source=None, controller="p1",
                      power=0, toughness=1, label="becomes 0/1")
    s.state.rules.effects = plan.state.rules.effects
    assert ch(s, cards, bear).pt == (0, 1)
    creature(s, "p1", "Godhead", "0/1", "Other creatures have base power and toughness 1/1.")
    assert ch(s, cards, bear).pt == (1, 1)


def test_flash_static_stays_manual():
    """702.8a / 113.6e: flash matters in hand, where a permanent's static doesn't apply (611.3b)."""
    assert statics.parse("~ has flash as long as you control a Desert.") is None
    assert statics.parse("Creatures you control have flash.") is None


def test_full_board_derive_is_fast(cards):
    """Conditions are evaluated once per static per table state, not once per affected object."""
    import time

    s = table(cards)
    creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.")
    creature(s, "p1", "Warden", "0/4", "Creatures you control get +2/+2 as long as you control three or more artifacts.")
    creature(s, "p1", "W2", "0/4", "Creatures you control have flying as long as you control a Mountain.")
    creature(s, "p1", "W3", "0/4", "Artifacts you control have shroud as long as you control three or more artifacts.")
    creature(s, "p1", "Kwende", "2/2", "Creatures you control with first strike have double strike.")
    creature(s, "p1", "Knight", "2/2", "Other creatures you control have first strike.")
    creature(s, "p2", "W4", "0/4", "Creatures you control have hexproof as long as you control no untapped lands.")
    creature(s, "p2", "Cumber", "0/4", "Creatures your opponents control get -1/-0.")
    creature(s, "p2", "Hoof", "0/4", "During your turn, creatures you control get +2/+0.")
    for i in range(35):
        creature(s, "p1", f"A{i}", "2/2")
    for i in range(36):
        creature(s, "p2", f"B{i}", "2/2")
    turn_on(s)
    plan = Plan(s.state, "p1", cards, None)
    field = [c for c in s.state.cards.values() if c.zone.endswith(":battlefield")]
    assert len(field) == 80
    for c in field:
        plan.ch(c)
    t0 = time.perf_counter()
    for c in field:
        plan.ch(c)
    elapsed = time.perf_counter() - t0
    a0 = next(c for c in field if c.name == "A0")
    assert ch(s, cards, a0).pt == (2, 3) and "double strike" in ch(s, cards, a0).keywords  # Banner, Cumber, Kwende
    assert elapsed < 0.5, f"{elapsed * 1000:.0f} ms for a pass over 80 permanents"  # (≈15 ms; was ≈300)
