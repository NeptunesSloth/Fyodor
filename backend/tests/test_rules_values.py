"""Dynamic values (app/rules/values.py): "the number of …", "for each …", "equal to …", X,
devotion (700.5), distinct card types (205.2a), halves (107.1), life totals; static "gets +N/+N
for each …" modifications (613.4c, read whenever looked at: 611.3a) and characteristic-defining
power/toughness (604.3, 613.4a) applied by app/rules/layers.py."""

from __future__ import annotations

import pytest

from app.rules import selectors, statics, values
from app.rules.language import parse_sentence
from app.rules.plan import Plan
from tests.game_helpers import act, turn_on, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_statics import token as statics_token


def key(phrase):
    return selectors.parse(phrase).key()


def ch(s, cards, card):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id])


# -- parsing: quantities ---------------------------------------------------------------------
@pytest.mark.parametrize(("phrase", "value"), [
    ("the number of creatures you control", {"count": key("creature you control")}),
    ("lands you control", {"count": key("lands you control")}),
    ("other creatures you control", {"count": key("other creatures you control")}),
    ("creature cards in your graveyard", {"count": key("creature cards in your graveyard")}),
    ("cards in all graveyards", {"count": key("cards in graveyards")}),
    ("instant and sorcery cards in your graveyard", {"count": key("instant or sorcery cards in your graveyard")}),
    ("cards in your hand", {"hand": "you"}),
    ("cards in target player's hand", {"hand": "target"}),
    ("opponents", {"opponents": 1}),
    ("players", {"count": key("players")}),
    ("+1/+1 counters on ~", {"counters": "+1/+1", "on": "self"}),
    ("charge counters on this artifact", {"counters": "charge", "on": "self"}),
    ("experience counters you have", {"player_counters": "experience"}),
    ("your life total", {"life": "you"}),
    ("the highest life total among your opponents", {"life": "opponent_max"}),
    ("your devotion to green", {"devotion": ["G"]}),
    ("your devotion to white and blue", {"devotion": ["W", "U"]}),
    ("the number of card types among cards in all graveyards", {"distinct": "types", "among": key("cards in graveyards")}),
    ("the number of basic land types among lands you control",
     {"distinct": "basic_land_types", "among": key("lands you control")}),
    ("colors among permanents you control", {"distinct": "colors", "among": key("permanents you control")}),
    ("twice the number of Elves you control", {"times": [2, {"count": key("Elves you control")}]}),
    ("half your life total, rounded up", {"half": {"life": "you"}, "round": "up"}),
    ("the number of Zombies you control plus one", {"plus": [{"count": key("Zombies you control")}, 1]}),
    ("the greatest power among creatures you control", {"max": "power", "of": key("creatures you control")}),
    ("the total power of creatures you control", {"sum": "power", "of": key("creatures you control")}),
    ("X", {"x": 1}),
])
def test_parse_count(phrase, value):
    assert values.parse_count(phrase) == value


@pytest.mark.parametrize("phrase", [
    "+1/+1 counters on it",  # a pronoun the caller can't bind
    "counters on target creature",  # (a target the value would have to declare)
    "Auras attached to it",
    "creatures that were exiled this turn",  # ("… that died this turn": read since wave 4D)
    "the amount of mana spent to cast it",
    "hone counters on ~",  # a counter kind the engine doesn't model
    "the number of foo you control",
])
def test_unknown_quantities_are_not_guessed(phrase):
    assert values.parse_count(phrase) is None


def test_counters_on_it_binds_only_when_the_caller_says_what_it_is():
    assert values.parse_count("oil counters on it", it="self") == {"counters": "oil", "on": "self"}


# -- parsing: sentences ----------------------------------------------------------------------
@pytest.mark.parametrize(("text", "n"), [
    ("~ deals damage to target creature equal to the number of lands you control", {"count": key("lands you control")}),
    ("~ deals damage equal to the number of creatures you control to target creature", {"count": key("creatures you control")}),
    ("~ deals damage equal to twice its power to target creature", {"times": [2, {"power": "self"}]}),
    ("~ deals damage equal to ~'s power to target creature", {"power": "self"}),
])
def test_damage_amounts(text, n):
    effects, target = parse_sentence(text)
    assert effects == [{"do": "damage", "who": "target", "n": n}] and target == key("creature")


def test_other_amounts():
    assert parse_sentence("you gain life equal to your devotion to white")[0] == [{"do": "gain_life", "who": "you", "n": {"devotion": ["W"]}}]
    assert parse_sentence("draw cards equal to the number of card types among cards in your graveyard")[0] == \
        [{"do": "draw", "who": "you", "n": {"distinct": "types", "among": key("cards in your graveyard")}}]
    assert parse_sentence("you lose life equal to half your life total, rounded up")[0] == \
        [{"do": "lose_life", "who": "you", "n": {"half": {"life": "you"}, "round": "up"}}]
    effects, target = parse_sentence("you gain life equal to the number of cards in target player's hand")
    assert effects == [{"do": "gain_life", "who": "you", "n": {"hand": "target"}}] and target == "player"
    assert parse_sentence("put a +1/+1 counter on ~ for each instant and sorcery card in your graveyard")[0] == \
        [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": {"count": key("instant or sorcery cards in your graveyard")}}]
    assert parse_sentence("you gain 2 life for each opponent")[0] == [{"do": "gain_life", "who": "you", "n": {"times": [2, {"opponents": 1}]}}]
    # 107.3c: one X, defined by the text, for the whole ability (Northern Air Temple)
    shrines = {"count": key("Shrines you control")}
    assert parse_sentence("each opponent loses X life and you gain X life, where X is the number of Shrines you control")[0] == \
        [{"do": "lose_life", "who": "each_opponent", "n": shrines}, {"do": "gain_life", "who": "you", "n": shrines}]


@pytest.mark.parametrize("text", [
    "draw a card for each Aura attached to it",
    "each opponent loses X life and you draw a card, where X is the number of Shrines you control",  # X in one half only
])
def test_unknown_sentences_stay_manual(text):
    assert parse_sentence(text) is None


# -- parsing: statics ------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "who", "each"), [
    ("~ gets +1/+0 for each artifact you control.", "self", {"p": 1, "t": 0, "value": {"count": key("artifacts you control")}}),
    ("~ gets -1/-1 for each card in your hand.", "self", {"p": -1, "t": -1, "value": {"hand": "you"}}),
    ("~ gets +1/+1 for each oil counter on it.", "self", {"p": 1, "t": 1, "value": {"counters": "oil", "on": "self"}}),
    ("~ gets +1/+1 for each experience counter you have.", "self", {"p": 1, "t": 1, "value": {"player_counters": "experience"}}),
    ("Creatures you control get +1/+1 for each Elf you control.", key("creatures you control"),
     {"p": 1, "t": 1, "value": {"count": key("Elves you control")}}),
    ("Equipped creature gets +1/+1 for each charge counter on ~.", "attached",
     {"p": 1, "t": 1, "value": {"counters": "charge", "on": "self"}}),
    ("Enchanted creature gets +1/+1 for each other creature you control.", "attached",
     {"p": 1, "t": 1, "value": {"count": key("other creatures you control")}}),
    ("~ gets +X/+X, where X is your life total.", "self", {"p": 1, "t": 1, "value": {"life": "you"}}),
    ("Enchanted creature gets -X/-0, where X is the number of cards in your graveyard.", "attached",
     {"p": -1, "t": 0, "value": {"count": key("cards in your graveyard")}}),
])
def test_parse_static_for_each(text, who, each):
    d = statics.parse(text)
    assert d is not None and d["static"] == "grant" and d["who"] == who and d["each"] == each
    assert (d["p"], d["t"]) == (0, 0)


@pytest.mark.parametrize(("text", "p", "t"), [
    ("~'s power and toughness are each equal to the number of lands you control.",
     {"count": key("lands you control")}, {"count": key("lands you control")}),
    ("~'s power is equal to the number of cards in your hand.", {"hand": "you"}, None),
    ("~'s toughness is equal to the number of Forests you control.", None, {"count": key("Forests you control")}),
    ("Domain — ~'s power is equal to the number of basic land types among lands you control.",
     {"distinct": "basic_land_types", "among": key("lands you control")}, None),
    ("~'s power is equal to the number of card types among cards in all graveyards and its toughness is equal to "
     "that number plus 1.", {"distinct": "types", "among": key("cards in graveyards")},
     {"plus": [{"distinct": "types", "among": key("cards in graveyards")}, 1]}),
    ("~'s power and toughness are each equal to your life total.", {"life": "you"}, {"life": "you"}),
    ("~'s power and toughness are each equal to your devotion to black.", {"devotion": ["B"]}, {"devotion": ["B"]}),
])
def test_parse_cda(text, p, t):
    assert statics.parse(text) == {"kind": "static", "static": "cda", "effects": [], "p": p, "t": t}


@pytest.mark.parametrize("text", [
    "Equipped creature gets +1/+1 for each Aura attached to another creature.",  # (wave 8D: "attached to it" is read)
    "Equipped creature gets +1/+1 for each +1/+1 counter on it.",  # "it" is the equipped creature, not the source
    "Creatures you control get +1/+1 for each counter on it.",
    "~ gets +1/+1 for each creature that attacked this turn.",
    "~ gets +X/+X.",  # no X defined
    "~ gets +1/+1, where X is your life total.",  # no X in the sentence
    "~'s power and toughness are each equal to the life paid as it entered.",
    "~'s power and toughness are each equal to the number of creatures you control as long as it's your turn.",
])
def test_unknown_statics_stay_manual(text):
    assert statics.parse(text) is None


# -- the table: statics with a dynamic amount (613.4c, 611.3a) -------------------------------
def test_static_for_each_is_read_whenever_looked_at(cards):
    s = table(cards)
    lasher = creature(s, "p1", "Lasher", "1/1", "~ gets +1/+0 for each artifact you control.")
    turn_on(s)
    assert ch(s, cards, lasher).pt == (1, 1)
    for i in range(2):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Cog{i}", "type_line": "Token Artifact"})
    assert ch(s, cards, lasher).pt == (3, 1)
    theirs = creature(s, "p2", "Mirror", "1/1", "~ gets +1/+0 for each artifact you control.")
    assert ch(s, cards, theirs).pt == (1, 1)  # "you" is its controller (613)
    cog = next(c for c in s.state.cards.values() if c.name == "Cog0")
    act(s, "p1", type="move", card_ids=[cog.id], to={"zone": "graveyard"})
    assert ch(s, cards, lasher).pt == (2, 1)
    replay_matches(s)


def test_static_for_each_counts_the_source_and_negative_amounts(cards):
    s = table(cards)
    strider = creature(s, "p1", "Strider", "7/7", "~ gets -1/-1 for each card in your hand.")
    lord = creature(s, "p1", "Lord", "2/2", "Creatures you control get +1/+1 for each Elf you control.")
    turn_on(s)
    assert ch(s, cards, strider).pt == (7, 7) and ch(s, cards, lord).pt == (2, 2)
    act(s, "p1", type="draw", player="p1", count=3)
    assert ch(s, cards, strider).pt == (4, 4)
    act(s, "p1", type="create_token", player="p1", token={"name": "Elf", "type_line": "Token Creature — Elf",
                                                          "power": "1", "toughness": "1"})
    elf = next(c for c in s.state.cards.values() if c.name == "Elf")
    assert ch(s, cards, lord).pt == (3, 3) and ch(s, cards, elf).pt == (2, 2) and ch(s, cards, strider).pt == (5, 5)
    replay_matches(s)


def test_other_in_a_static_count_means_other_than_the_affected_object(cards):
    """Bravado: "Enchanted creature gets +1/+1 for each other creature you control" — the
    enchanted creature doesn't count itself; Heroes' Podium: each legendary creature counts the
    OTHER legendary creatures."""
    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    creature(s, "p1", "Pal", "1/1")
    aura = statics_token(s, "p1", "Bravado", "Token Enchantment — Aura",
                         "Enchanted creature gets +1/+1 for each other creature you control.")
    act(s, "p1", type="attach", card_ids=[aura.id], to=bear.id)  # (704.5m: an unattached Aura would go)
    turn_on(s)
    assert ch(s, cards, bear).pt == (3, 3)  # the Pal only
    statics_token(s, "p1", "Podium", "Token Artifact",
                  "Each legendary creature you control gets +1/+1 for each other legendary creature you control.")
    for name in ("King", "Queen"):
        act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Legendary Token Creature — Noble",
                                                              "power": "2", "toughness": "2"})
    king = next(c for c in s.state.cards.values() if c.name == "King")
    assert ch(s, cards, king).pt == (3, 3)  # the Queen; not itself
    replay_matches(s)


def test_static_for_each_counter_on_the_source_and_x_from_life(cards):
    s = table(cards)
    drake = creature(s, "p1", "Drake", "1/1", "~ gets +1/+1 for each oil counter on it.")
    avatar = creature(s, "p1", "Avatar", "0/0", "~ gets +X/+X, where X is your life total.")
    turn_on(s)
    act(s, "p1", type="counter", card_ids=[drake.id], kind="oil", delta=3)
    assert ch(s, cards, drake).pt == (4, 4)
    assert ch(s, cards, avatar).pt == (40, 40)
    act(s, "p1", type="life", player="p1", delta=-5)
    assert ch(s, cards, avatar).pt == (35, 35)
    replay_matches(s)


# -- the table: characteristic-defining power/toughness (604.3, 613.4a) -----------------------
def colossus(s, pid, name, text, pt="*/*"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Golem",
                                                       "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def land(s, pid, name="Forest"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token Land — {name}"})


def test_cda_counts_lands_as_they_come_and_go(cards):
    s = table(cards)
    land(s, "p1")
    land(s, "p1")
    big = colossus(s, "p1", "Colossus", "~'s power and toughness are each equal to the number of lands you control.")
    turn_on(s)
    assert ch(s, cards, big).pt == (2, 2)
    land(s, "p1")
    assert ch(s, cards, big).pt == (3, 3)
    land(s, "p2")
    assert ch(s, cards, big).pt == (3, 3)  # theirs don't count
    replay_matches(s)


def test_cda_creature_with_nothing_to_count_is_zero_and_dies(cards):
    s = table(cards)
    big = colossus(s, "p1", "Colossus", "~'s power and toughness are each equal to the number of lands you control.")
    turn_on(s)  # 704.5f: toughness 0 → the graveyard, where a token ceases to exist (704.5d)
    assert big.id not in s.state.cards
    replay_matches(s)


def test_cda_works_in_every_zone(cards):
    """604.3: Master of Etherium is a 1/1 in your hand with one artifact out, counts itself on the
    battlefield, and is still computed in the graveyard (a card with no controller reads its
    owner, 108.4a)."""
    s = build(cards, "Master of Etherium")
    to_hand(s, "Master of Etherium")
    master = named(s, "Master of Etherium")
    act(s, "p1", type="create_token", player="p1", token={"name": "Cog", "type_line": "Token Artifact"})
    assert ch(s, cards, master).pt == (1, 1)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=master.id)
    pass_until_stack_empty(s)
    assert s.state.cards[master.id].zone == "p1:battlefield" and ch(s, cards, master).pt == (2, 2)
    act(s, "p1", type="move", card_ids=[master.id], to={"zone": "graveyard"})
    assert ch(s, cards, master).pt == (1, 1)
    replay_matches(s)


def test_cda_power_only_with_counters_and_a_lord(cards):
    s = table(cards)
    djinn = colossus(s, "p1", "Djinn", "~'s power is equal to the number of cards in your hand.", pt="*/4")
    creature(s, "p1", "Banner", "0/4", "Other creatures you control get +1/+1.")
    turn_on(s)
    act(s, "p1", type="draw", player="p1", count=2)
    act(s, "p1", type="counter", card_ids=[djinn.id], kind="+1/+1", delta=1)
    assert ch(s, cards, djinn).pt == (2 + 1 + 1, 4 + 1 + 1)  # 7a, then 7c: the anthem and the counter
    replay_matches(s)


def test_cda_distinct_card_types_in_graveyards_plus_one(cards):
    s = table(cards)
    goyf = colossus(s, "p1", "Goyf", "~'s power is equal to the number of card types among cards in all graveyards "
                                     "and its toughness is equal to that number plus 1.")
    turn_on(s)
    assert ch(s, cards, goyf).pt == (0, 1)
    forest = next(s.state.cards[c] for c in zone(s.state, "p1", "library") if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
    assert ch(s, cards, goyf).pt == (1, 2)
    theirs = next(s.state.cards[c] for c in zone(s.state, "p2", "library") if s.state.cards[c].name == "Forest")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
    assert ch(s, cards, goyf).pt == (1, 2)  # a second land: the same type (205.2a)
    replay_matches(s)


def test_cda_is_not_computed_for_a_card_played_by_hand(cards):
    s = table(cards)
    land(s, "p1")
    big = colossus(s, "p1", "Colossus", "~'s power and toughness are each equal to the number of lands you control.")
    turn_on(s)
    s.state.rules.card_modes[big.id] = "manual"
    assert ch(s, cards, big).pt is None


# -- resolution --------------------------------------------------------------------------
def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def test_damage_equal_to_the_number_of_lands(cards):
    s = build(cards)
    for _ in range(3):
        land(s, "p1")
    wall = token(s, "p2", "Wall", "0/5")
    src = token(s, "p1", "Slide", text="{1}: This creature deals damage to target creature equal to the number of lands you control.")
    activate(s, src, targets=[wall.id])
    assert s.state.cards[wall.id].damage == 3
    replay_matches(s)


def test_devotion_counts_mana_symbols_of_permanents_you_control(cards):
    s = build(cards, "Llanowar Elves")
    to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=next(c for c in zone(s.state, "p1", "hand")
                                                 if s.state.cards[c].name == "Llanowar Elves"))
    pass_until_stack_empty(s)
    src = token(s, "p1", "Idol", text="{1}: You gain life equal to your devotion to green.")
    activate(s, src)
    assert s.state.players["p1"].life == 41  # {G}: one green symbol (the tokens have no mana cost)
    replay_matches(s)


def test_half_life_rounded_and_a_target_players_hand(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=3)
    src = token(s, "p1", "Pact", text="{1}: You lose life equal to half your life total, rounded up.")
    activate(s, src)
    assert s.state.players["p1"].life == 20
    act(s, "p1", type="life", player="p1", delta=-3)  # 17 → half rounded up is 9
    activate(s, src)
    assert s.state.players["p1"].life == 8
    spy = token(s, "p1", "Spy", text="{1}: You gain life equal to the number of cards in target player's hand.")
    activate(s, spy, targets=["p2"])
    assert s.state.players["p1"].life == 8 + len(zone(s.state, "p2", "hand"))
    replay_matches(s)


def test_distinct_card_types_and_opponent_counts(cards):
    s = build(cards)
    forest = next(s.state.cards[c] for c in zone(s.state, "p1", "library") if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
    src = token(s, "p1", "Scholar", text="{1}: Draw cards equal to the number of card types among cards in your graveyard.")
    before = len(zone(s.state, "p1", "hand"))
    activate(s, src)
    assert len(zone(s.state, "p1", "hand")) == before + 1
    gift = token(s, "p1", "Gift", text="{1}: You gain 2 life for each opponent.")
    activate(s, gift)
    assert s.state.players["p1"].life == 42
    replay_matches(s)


def test_x_from_the_activation_cost(cards):
    s = build(cards)
    src = token(s, "p1", "Fountain", text="{X}: You gain X life.")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, x_value=3)
    pass_until_stack_empty(s)
    assert s.state.players["p1"].life == 43
    replay_matches(s)


def test_each_opponent_discards_for_each_privately(cards):
    """The count is public; the discard is the opponent's private choice (the non-chooser sees no options)."""
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=4)
    land(s, "p1")
    land(s, "p1")
    src = token(s, "p1", "Rot", text="{1}: Each opponent discards a card for each land you control.")
    activate(s, src)
    d = s.state.rules.decision
    assert d.player == "p2" and d.min_choices == 2
    assert s.view("p1")["rules"]["decision"].get("options") is None
    hand = zone(s.state, "p2", "hand")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=hand[:2])
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p2", "graveyard")) == 2
    replay_matches(s)


# -- primitives added by agent G (app/rules/effects.py: pump values, fight, bite) ----------------------
def test_pump_with_a_dynamic_amount(cards):
    effects, target = parse_sentence("target creature gets +x/+0 until end of turn")
    assert effects == [{"do": "pump", "who": "target", "p": {"x": 1}, "t": 0}]


def test_fight(cards):
    effects, targets = parse_sentence("target creature you control fights target creature you don't control")
    assert effects == [{"do": "fight", "who": "target", "with": "target:1"}]


def test_bite(cards):
    effects, targets = parse_sentence("target creature you control deals damage equal to its power to target creature you don't control")
    assert effects == [{"do": "damage", "who": "target:1", "n": {"power": "target"}, "src": "target"}]


def test_counters_on_it_binds_through_the_pronoun_resolver():
    """"on": "it" is a placeholder like {"power": "it"}: scripts.resolve_it binds it to the object
    the ability named (agent G: scripts._STAT_KEYS), or the ability stays manual."""
    from app.rules.scripts import parse_effects

    assert parse_sentence("draw a card for each +1/+1 counter on it")[0] == \
        [{"do": "draw", "who": "you", "n": {"counters": "+1/+1", "on": "it"}}]
    assert parse_effects("Draw a card for each +1/+1 counter on it.") is None  # (nothing to bind "it" to)
    assert parse_effects("Draw a card for each +1/+1 counter on it.", it="self")[0] == \
        [{"do": "draw", "who": "you", "n": {"counters": "+1/+1", "on": "self"}}]


def test_that_players_hand_binds_only_to_a_target_player_or_the_triggers_player():
    """(wave 3R4) "cards in that player's hand" is a placeholder the ability-level parse binds (scripts._that_players_hand):
    the target player, or the trigger's player named by "that player"; anything else stays manual."""
    from app.rules.scripts import parse_effects

    assert values.parse_count("cards in that player's hand") == {"hand": "that_player"}
    assert parse_effects("~ deals damage to target creature equal to the number of cards in that player's hand.") is None
    found = parse_effects("~ deals damage to target player equal to the number of cards in that player's hand.")
    assert found is not None and found[0][0]["n"] == {"hand": "target"}
