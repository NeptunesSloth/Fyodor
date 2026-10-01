"""Forms that were refused (left manual) in the modal and conditional families, now read (wave 3R1).

* How a spell was cast (601.2h payment record; 603.4 intervening "if"; 707.10 a copy isn't cast): "if you cast it
  [from your hand]", "if this spell was cast from a graveyard" / "from anywhere other than your hand", "if {R} was
  spent to cast it", adamant, addendum ("if you cast this spell during your main phase").

Every scenario uses real Commander-legal cards with their current Oracle text (data/cards.sqlite) and checks that
replaying the recorded history reproduces the table.
"""

from __future__ import annotations

import pytest

from app.rules import conditions
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, cast, life, settle, to_hand
from tests.test_rules_effects import mana, replay_matches, run_until

EXTRA = [
    card('Feasting Troll King', set_code="tst", number="R100", mana_cost='{2}{G}{G}{G}{G}', cmc=6.0, type_line='Creature — Troll Noble', oracle_text='Vigilance, trample\nWhen this creature enters, if you cast it from your hand, create three Food tokens. (They\'re artifacts with "{2}, {T}, Sacrifice this token: You gain 3 life.")\nSacrifice three Foods: Return this card from your graveyard to the battlefield. Activate only during your turn.', power='7', toughness='6', colors=['G'], color_identity=['G'], keywords=['Vigilance', 'Food', 'Trample']),
    card('Gruul Scrapper', set_code="tst", number="R101", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Berserker', oracle_text='When this creature enters, if {R} was spent to cast it, it gains haste until end of turn.', power='3', toughness='2', colors=['G'], color_identity=['G', 'R']),
    card('Azorius Herald', set_code="tst", number="R102", mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Spirit', oracle_text="This creature can't be blocked.\nWhen this creature enters, you gain 4 life.\nWhen this creature enters, sacrifice it unless {U} was spent to cast it.", power='2', toughness='1', colors=['W'], color_identity=['U', 'W']),
    card('Seed Spark', set_code="tst", number="R103", mana_cost='{3}{W}', cmc=4.0, type_line='Instant', oracle_text='Destroy target artifact or enchantment. If {G} was spent to cast this spell, create two 1/1 green Saproling creature tokens.', colors=['W'], color_identity=['G', 'W']),
    card('Haunting Hymn', set_code="tst", number="R104", mana_cost='{4}{B}{B}', cmc=6.0, type_line='Instant', oracle_text='Target player discards two cards. If you cast this spell during your main phase, that player discards four cards instead.', colors=['B'], color_identity=['B']),
    card('Clockwork Servant', set_code="tst", number="R105", mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Gnome', oracle_text='Adamant — When this creature enters, if at least three mana of the same color was spent to cast it, draw a card.', power='2', toughness='3', keywords=['Adamant']),
    card('Cacophony Unleashed', set_code="tst", number="R106", mana_cost='{5}{B}{B}', cmc=7.0, type_line='Enchantment', oracle_text="When this enchantment enters, if you cast it, destroy all nonenchantment creatures.\nWhenever this enchantment or another enchantment you control enters, until end of turn, this enchantment becomes a legendary 6/6 Nightmare God creature with menace and deathtouch. It's still an enchantment.", colors=['B'], color_identity=['B']),
    card('Armory Mice', set_code="tst", number="R108", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Mouse', oracle_text='Celebration — This creature gets +0/+2 as long as two or more nonland permanents entered the battlefield under your control this turn.', power='3', toughness='1', colors=['W'], color_identity=['W'], keywords=['Celebration']),
    card('Wary Farmer', set_code="tst", number="R109", mana_cost='{1}{G/W}{G/W}', cmc=3.0, type_line='Creature — Kithkin Citizen', oracle_text='At the beginning of your end step, if another creature entered the battlefield under your control this turn, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)', power='3', toughness='3', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Surveil']),
    card('Crew Captain', set_code="tst", number="R110", mana_cost='{B}{R}{G}', cmc=3.0, type_line='Creature — Human Warrior', oracle_text='Haste\nThis creature has indestructible as long as it entered this turn.', power='4', toughness='2', colors=['B', 'G', 'R'], color_identity=['B', 'G', 'R'], keywords=['Haste']),
    card('Ardenvale Paladin', set_code="tst", number="R111", mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Human Knight', oracle_text='Adamant — If at least three white mana was spent to cast this spell, this creature enters with a +1/+1 counter on it.', power='2', toughness='5', colors=['W'], color_identity=['W'], keywords=['Adamant']),
    card('Increasing Savagery', set_code="tst", number="R107", mana_cost='{2}{G}{G}', cmc=4.0, type_line='Sorcery', oracle_text='Put five +1/+1 counters on target creature. If this spell was cast from a graveyard, put ten +1/+1 counters on that creature instead.\nFlashback {5}{G}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['G'], color_identity=['G'], keywords=['Flashback']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def on_field_names(s, pid="p1"):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:battlefield", []))


# -- how a spell was cast ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("you cast it", {"object": "it", "cast": {"by_you": True}}),  # Cacophony Unleashed
    ("it was cast", {"object": "it", "cast": {"by_you": False}}),  # Doomsday Excruciator
    ("you cast it from your hand", {"object": "it", "cast": {"by_you": True, "from": "hand"}}),  # Feasting Troll King
    ("this spell was cast from a graveyard", {"object": "self", "cast": {"by_you": False, "from": "graveyard"}}),  # Increasing Savagery
    ("this spell was cast from anywhere other than your hand",
     {"object": "self", "cast": {"by_you": False, "from": "!hand"}}),  # Antiquities on the Loose
    ("you cast this spell during your main phase", {"object": "self", "cast": {"by_you": True, "main": True}}),  # Haunting Hymn
    ("{R} was spent to cast it", {"object": "it", "cast": {"spent": {"R": 1}}}),  # Gruul Scrapper
    ("{U}{B} was spent to cast this spell", {"object": "self", "cast": {"spent": {"U": 1, "B": 1}}}),  # Mythos of Brokkos
    ("{W}{W} was spent to cast it", {"object": "it", "cast": {"spent": {"W": 2}}}),  # Catharsis
    ("at least three white mana was spent to cast this spell", {"object": "self", "cast": {"spent": {"W": 3}}}),  # Ardenvale Paladin
    ("at least three mana of the same color was spent to cast it", {"object": "it", "cast": {"same_color": 3}}),  # Clockwork Servant
    ("five or more mana was spent to cast it", {"object": "it", "cast": {"total": 5}}),
])
def test_cast_wordings(text, expected):
    assert conditions.parse(text, objects=True) == expected
    assert conditions.parse(text) is None  # (only where the ability has objects)


@pytest.mark.parametrize("text", [
    "{S} was spent to cast it",  # Berg Strider: what made the mana (snow) isn't recorded
    "mana from a Treasure was spent to cast it",  # Hired Hexblade
    "five or more mana was spent to cast that spell",  # Elemental Mascot: another spell's record is gone once it resolved
    "it was cast during your main phase",
])
def test_cast_wordings_refused(text):
    assert conditions.parse(text, objects=True) is None


def test_if_you_cast_it_from_your_hand(cards):
    """Feasting Troll King: cast from hand, three Foods; put onto the battlefield (not cast), none (603.4)."""
    s = build(cards, "Feasting Troll King")
    troll = to_hand(s, "Feasting Troll King")
    mana(s, G=6)
    cast(s, troll)
    assert on_field_names(s).count("Food") == 3
    act(s, "p1", type="move", card_ids=[troll.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[troll.id], to={"player": "p1", "zone": "battlefield"})
    settle(s)
    assert on_field_names(s).count("Food") == 3  # (put onto the battlefield, not cast: the ability doesn't trigger)
    replay_matches(s)


def test_cast_by_hand_counts_as_cast_but_mana_is_unknown(cards):
    """A card moved onto the stack by hand was cast (the engine counts it): Feasting Troll King's Foods come; what
    paid for it isn't known, so Gruul Scrapper's "if {R} was spent" never holds."""
    s = build(cards, "Feasting Troll King", "Gruul Scrapper")
    troll, scrapper = to_hand(s, "Feasting Troll King"), to_hand(s, "Gruul Scrapper")
    act(s, "p1", type="move", card_ids=[troll.id], to={"zone": "stack"})
    act(s, "p1", type="pass_priority")
    settle(s)
    assert s.state.cards[troll.id].zone == "p1:battlefield" and on_field_names(s).count("Food") == 3
    act(s, "p1", type="move", card_ids=[scrapper.id], to={"zone": "stack"})
    act(s, "p1", type="pass_priority")
    settle(s)
    assert s.state.cards[scrapper.id].zone == "p1:battlefield"
    assert "haste" not in _keywords(s, scrapper)
    replay_matches(s)


def _keywords(s, c):
    from app.rules.plan import Plan

    plan = Plan.view(s.state, "p1", s.cards)
    return plan.ch(s.state.cards[c.id]).keywords


@pytest.mark.parametrize(("pool", "haste"), [({"G": 3, "R": 1}, True), ({"G": 4}, False)])
def test_mana_spent_to_cast_it(cards, pool, haste):
    """Gruul Scrapper ({3}{G}): haste only if {R} paid part of its cost (601.2h: the mana actually spent)."""
    s = build(cards, "Gruul Scrapper")
    scrapper = to_hand(s, "Gruul Scrapper")
    mana(s, **pool)
    cast(s, scrapper)
    assert ("haste" in _keywords(s, scrapper)) is haste
    replay_matches(s)


@pytest.mark.parametrize(("pool", "stays"), [({"W": 2, "U": 1}, True), ({"W": 3}, False)])
def test_sacrifice_it_unless_mana_was_spent(cards, pool, stays):
    """Azorius Herald: "sacrifice it unless {U} was spent to cast it"; its other trigger gains 4 life either way."""
    s = build(cards, "Azorius Herald")
    herald = to_hand(s, "Azorius Herald")
    mana(s, **pool)
    cast(s, herald)
    assert (s.state.cards[herald.id].zone == "p1:battlefield") is stays
    assert life(s) == 44
    replay_matches(s)


def test_adamant_same_color(cards):
    """Clockwork Servant ({3}): three mana of one color draws a card; three different colors don't."""
    s = build(cards, "Clockwork Servant", "Clockwork Servant")
    first, second = [c for c in s.state.cards.values() if c.name == "Clockwork Servant"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=3)
    cast(s, first)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1
    mana(s, R=1, G=1, B=1)
    cast(s, second)
    assert len(s.state.zones["p1:hand"]) == hand - 1
    replay_matches(s)


def test_spell_mana_spent_and_copy_not_cast(cards):
    """Seed Spark: {G} spent makes two Saprolings; paid with {W} only, none."""
    s = build(cards, "Seed Spark", "Seed Spark")
    one, two = [c for c in s.state.cards.values() if c.name == "Seed Spark"]
    for c in (one, two):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, "p2", type="create_token", player="p2", token={"name": "Relic", "type_line": "Token Artifact", "text": ""})
    act(s, "p2", type="create_token", player="p2", token={"name": "Relic2", "type_line": "Token Artifact", "text": ""})
    relic, relic2 = named(s, "Relic", "p2"), named(s, "Relic2", "p2")
    mana(s, W=1, G=3)
    cast(s, one, targets=[relic.id])
    assert on_field_names(s).count("Saproling") == 2
    mana(s, W=4)
    cast(s, two, targets=[relic2.id])
    assert on_field_names(s).count("Saproling") == 2
    replay_matches(s)


def test_cast_from_a_graveyard_instead(cards):
    """Increasing Savagery: five counters from hand; ten with flashback from the graveyard (702.34a)."""
    s = build(cards, "Increasing Savagery")
    act(s, "p1", type="create_token", player="p1", token={"name": "Bear", "type_line": "Token Creature — Bear",
                                                           "power": "2", "toughness": "2", "text": ""})
    bear = named(s, "Bear")
    savagery = to_hand(s, "Increasing Savagery")
    mana(s, G=4)
    cast(s, savagery, targets=[bear.id])
    assert s.state.cards[bear.id].counters.get("+1/+1") == 5
    assert s.state.cards[savagery.id].zone == "p1:graveyard"
    mana(s, G=7)
    cast(s, savagery, targets=[bear.id])
    assert s.state.cards[bear.id].counters.get("+1/+1") == 15
    assert s.state.cards[savagery.id].zone == "p1:exile"
    replay_matches(s)


def test_addendum_main_phase_only_on_your_turn(cards):
    """Haunting Hymn: cast in your main phase, four discards; during an opponent's turn, two (505.1: "your main phase")."""
    s = build(cards, "Haunting Hymn", "Haunting Hymn", p2=["Island"] * 0)
    one, two = [c for c in s.state.cards.values() if c.name == "Haunting Hymn"]
    for c in (one, two):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    bob_hand = s.state.zones["p2:hand"]
    for c in [c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:library"][:6]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    before = len(s.state.zones["p2:hand"])
    mana(s, B=6)
    cast(s, one, targets=["p2"])
    assert len(s.state.zones["p2:hand"]) == before - 4
    act(s, "p1", type="set_prefs", response="on")
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.rules.priority == "p1")
    mana(s, B=6)
    act(s, "p1", type="cast_spell", card_id=two.id, targets=["p2"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == before - 6
    assert bob_hand is not None
    replay_matches(s)


def test_if_you_cast_it_rechecked_on_resolution_after_it_left(cards):
    """Cacophony Unleashed: "if you cast it" is still true as the trigger resolves after the enchantment left
    (603.4: checked again; how it was cast is a fact about that object, 608.2h)."""
    s = build(cards, "Cacophony Unleashed")
    caco = to_hand(s, "Cacophony Unleashed")
    act(s, "p2", type="create_token", player="p2", token={"name": "Bear", "type_line": "Token Creature — Bear",
                                                           "power": "2", "toughness": "2", "text": ""})
    act(s, "p2", type="set_prefs", response="on")
    mana(s, B=7)
    act(s, "p1", type="cast_spell", card_id=caco.id)
    for _ in range(10):
        if s.state.cards[caco.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    if d is not None and d.kind == "order":  # (its two "enters" triggers)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    assert any(e.name == "Cacophony Unleashed" for e in s.state.rules.stack.values()), (
        s.state.rules.decision, s.state.rules.stack, s.state.rules.pending_triggers)
    act(s, "p1", type="move", card_ids=[caco.id], to={"player": "p1", "zone": "graveyard"})
    settle(s)
    assert "Bear" not in on_field_names(s, "p2")
    replay_matches(s)


@pytest.mark.parametrize(("pool", "counter"), [({"W": 3, "G": 1}, 1), ({"W": 1, "G": 3}, 0)])
def test_adamant_enters_with_a_counter(cards, pool, counter):
    """Ardenvale Paladin: "If at least three white mana was spent to cast this spell, this creature enters with a
    +1/+1 counter on it." (614.1c, read from what paid its cost, 601.2h)."""
    s = build(cards, "Ardenvale Paladin")
    paladin = to_hand(s, "Ardenvale Paladin")
    mana(s, **pool)
    cast(s, paladin)
    assert s.state.cards[paladin.id].counters.get("+1/+1", 0) == counter
    replay_matches(s)


# -- what entered the battlefield this turn (608.2i) ------------------------------------------------------
def _pt(s, c):
    from app.rules.plan import Plan

    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def until_turn(s, number):
    """Play on (no attacks, first options) until turn ``number``'s first main phase; the prompts seen."""
    seen = []
    for _ in range(200):
        if s.state.turn.number == number and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            return seen
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            seen.append(d.prompt or d.kind)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def test_celebration_counts_nonland_permanents_that_entered(cards):
    """Armory Mice: +0/+2 once two nonland permanents entered under your control this turn — itself counts, a land
    doesn't, a token that entered and left still does (608.2i: it needn't still be there); next turn it starts over."""
    s = build(cards, "Armory Mice")
    mice = to_hand(s, "Armory Mice")
    mana(s, W=2)
    cast(s, mice)
    assert _pt(s, mice) == (3, 1)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    assert _pt(s, mice) == (3, 1)
    act(s, "p2", type="create_token", player="p2", token={"name": "Theirs", "type_line": "Token Creature — Bear",
                                                           "power": "2", "toughness": "2", "text": ""})
    assert _pt(s, mice) == (3, 1)  # (under another player's control)
    act(s, "p1", type="create_token", player="p1", token={"name": "Mine", "type_line": "Token Artifact — Clue", "text": ""})
    assert _pt(s, mice) == (3, 3)
    act(s, "p1", type="move", card_ids=[named(s, "Mine").id], to={"player": "p1", "zone": "graveyard"})
    assert _pt(s, mice) == (3, 3)
    until_turn(s, 3)
    assert _pt(s, mice) == (3, 1)
    replay_matches(s)


def test_another_creature_entered_and_entered_this_turn(cards):
    """Wary Farmer surveils at your end step only if another creature entered under your control this turn (not
    itself); Crew Captain is indestructible only during the turn it entered."""
    s = build(cards, "Wary Farmer", "Crew Captain")
    farmer, captain = to_hand(s, "Wary Farmer"), to_hand(s, "Crew Captain")
    mana(s, G=3)
    cast(s, farmer)
    assert not any("urveil" in p for p in until_turn(s, 3))
    mana(s, B=1, R=1, G=1)
    cast(s, captain)
    assert "indestructible" in _keywords(s, captain)
    assert any("urveil" in p for p in until_turn(s, 5))
    assert "indestructible" not in _keywords(s, captain)
    replay_matches(s)
