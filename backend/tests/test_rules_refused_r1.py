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
    card('Promise of Bunrei', set_code="tst", number="R113", mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment', oracle_text='When a creature you control dies, sacrifice this enchantment. If you do, create four 1/1 colorless Spirit creature tokens.', colors=['W'], color_identity=['W']),
    card('Woeleecher', set_code="tst", number="R114", mana_cost='{5}{W}', cmc=6.0, type_line='Creature — Elemental', oracle_text='{W}, {T}: Remove a -1/-1 counter from target creature. If you do, you gain 2 life.', power='3', toughness='5', colors=['W'], color_identity=['W']),
    card('Noosegraf Mob', set_code="tst", number="R115", mana_cost='{4}{B}{B}', cmc=6.0, type_line='Creature — Zombie', oracle_text='This creature enters with five +1/+1 counters on it.\nWhenever a player casts a spell, remove a +1/+1 counter from this creature. If you do, create a 2/2 black Zombie creature token.', power='0', toughness='0', colors=['B'], color_identity=['B']),
    card('Malakir Blood-Priest', set_code="tst", number="R117", mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Vampire Cleric', oracle_text='When this creature enters, each opponent loses X life and you gain X life, where X is the number of creatures in your party. (Your party consists of up to one each of Cleric, Rogue, Warrior, and Wizard.)', power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Hexgold Slash', set_code="tst", number="R119", mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Hexgold Slash deals 2 damage to target creature. If that creature has toxic, Hexgold Slash deals 4 damage to that creature instead.', colors=['R'], color_identity=['R']),
    card('Burn the Impure', set_code="tst", number="R120", mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text="Burn the Impure deals 3 damage to target creature. If that creature has infect, Burn the Impure deals 3 damage to that creature's controller.", colors=['R'], color_identity=['R']),
    card('Cavalier of Night', set_code="tst", number="R121", mana_cost='{2}{B}{B}{B}', cmc=5.0, type_line='Creature — Elemental Knight', oracle_text='Lifelink\nWhen this creature enters, you may sacrifice another creature. When you do, destroy target creature an opponent controls.\nWhen this creature dies, return target creature card with mana value 3 or less from your graveyard to the battlefield.', power='4', toughness='5', colors=['B'], color_identity=['B'], keywords=['Lifelink']),
    card('Brokers Hideout', set_code="tst", number="R122", cmc=0.0, type_line='Land', oracle_text='When this land enters, sacrifice it. When you do, search your library for a basic Forest, Plains, or Island card, put it onto the battlefield tapped, then shuffle and you gain 1 life.'),
    card("Caesar, Legion's Emperor", set_code="tst", number="R124", mana_cost='{1}{R}{W}{B}', cmc=4.0, type_line='Legendary Creature — Human Soldier', oracle_text='Whenever you attack, you may sacrifice another creature. When you do, choose two —\n• Create two 1/1 red and white Soldier creature tokens with haste that are tapped and attacking.\n• You draw a card and you lose 1 life.\n• Caesar deals damage equal to the number of creature tokens you control to target opponent.', power='4', toughness='4', colors=['B', 'R', 'W'], color_identity=['B', 'R', 'W']),
    card('Cult of Skaro', set_code="tst", number="R125", mana_cost='{1}{U}{B}{R}', cmc=4.0, type_line='Legendary Artifact Creature — Dalek', oracle_text='Whenever Cult of Skaro attacks, choose one at random —\n• Thay — Put a +1/+1 counter on each artifact creature you control.\n• Caan — Draw two cards.\n• Sec — Create a 3/3 black Dalek artifact creature token with menace.\n• Jast — Each opponent loses 4 life.', power='4', toughness='4', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Sec', 'Caan', 'Jast', 'Thay']),
    card('Prophetic Titan', set_code="tst", number="R126", mana_cost='{4}{U}{R}', cmc=6.0, type_line='Creature — Giant Wizard', oracle_text='Delirium — When this creature enters, choose one. If there are four or more card types among cards in your graveyard, choose both instead.\n• This creature deals 4 damage to any target.\n• Look at the top four cards of your library. Put one of them into your hand and the rest on the bottom of your library in a random order.', power='4', toughness='4', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Delirium']),
    card('Vindictive Lich', set_code="tst", number="R127", mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Zombie Wizard', oracle_text='When this creature dies, choose one or more. Each mode must target a different player.\n• Target opponent sacrifices a creature of their choice.\n• Target opponent discards two cards.\n• Target opponent loses 5 life.', power='4', toughness='1', colors=['B'], color_identity=['B']),
    card('Academy Rector', set_code="tst", number="R128", mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Human Cleric', oracle_text='When this creature dies, you may exile it. If you do, search your library for an enchantment card, put that card onto the battlefield, then shuffle.', power='1', toughness='2', colors=['W'], color_identity=['W']),
    card('Martial Coup', set_code="tst", number="R129", mana_cost='{X}{W}{W}', cmc=2.0, type_line='Sorcery', oracle_text='Create X 1/1 white Soldier creature tokens. If X is 5 or more, destroy all other creatures.', colors=['W'], color_identity=['W']),
    card('Consign to Dream', set_code="tst", number="R130", mana_cost='{2}{U}', cmc=3.0, type_line='Instant', oracle_text="Return target permanent to its owner's hand. If that permanent is red or green, put it on top of its owner's library instead.", colors=['U'], color_identity=['U']),
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
    # opus (wave 9C): a cast trigger's spell is still on the stack while the trigger resolves, so its record is read
    ("five or more mana was spent to cast that spell", {"object": "it", "cast": {"total": 5, "event_spell": True}}),
])
def test_cast_wordings(text, expected):
    assert conditions.parse(text, objects=True) == expected
    assert conditions.parse(text) is None  # (only where the ability has objects)


@pytest.mark.parametrize("text", [
    # (-- mana provenance (wave 18B) -- "{S} was spent" and "mana from a Treasure was spent" are read now: test_rules_wave18b_mana.py)
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


# -- "If you do" after an instruction that isn't optional (608.2c) ------------------------------------------
def _creature(s, pid, name, text=""):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Bear", "power": "2",
                                                         "toughness": "2", "text": text})
    return named(s, name, pid)


def test_sacrifice_this_if_you_do(cards):
    """Promise of Bunrei: two creatures die at once — two triggers; the first sacrifices it and makes four Spirits,
    the second can't sacrifice it (701.21a: it's gone), so it makes none."""
    s = build(cards, "Promise of Bunrei")
    promise = next(c for c in s.state.cards.values() if c.name == "Promise of Bunrei")
    act(s, "p1", type="move", card_ids=[promise.id], to={"player": "p1", "zone": "battlefield"})
    a, b = _creature(s, "p1", "Alpha"), _creature(s, "p1", "Beta")
    act(s, "p1", type="set_damage", card_ids=[a.id, b.id], delta=2)
    act(s, "p1", type="pass_priority")  # (both die at once: 704.5g)
    settle(s)
    assert s.state.cards[promise.id].zone == "p1:graveyard"
    assert on_field_names(s).count("Spirit") == 4
    replay_matches(s)


@pytest.mark.parametrize(("counters", "gained"), [(1, 2), (0, 0)])
def test_remove_a_counter_if_you_do(cards, counters, gained):
    """Woeleecher: no -1/-1 counter to remove, no life (122.8: nothing was removed)."""
    s = build(cards, "Woeleecher")
    leecher = next(c for c in s.state.cards.values() if c.name == "Woeleecher")
    act(s, "p1", type="move", card_ids=[leecher.id], to={"player": "p1", "zone": "battlefield"})
    until_turn(s, 3)  # (no longer summoning sick, 302.6)
    bear = _creature(s, "p2", "Bear")
    if counters:
        act(s, "p1", type="counter", card_ids=[bear.id], kind="-1/-1", delta=counters)
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=leecher.id, ability=0, targets=[bear.id])
    settle(s)
    assert life(s) == 40 + gained
    assert s.state.cards[bear.id].counters.get("-1/-1", 0) == 0
    replay_matches(s)


def test_remove_a_counter_from_this_creature_each_spell(cards):
    """Noosegraf Mob (five +1/+1 counters): each spell removes one and makes a Zombie; with none left, no Zombie."""
    s = build(cards, "Noosegraf Mob", "Gruul Scrapper")
    mob = next(c for c in s.state.cards.values() if c.name == "Noosegraf Mob")
    act(s, "p1", type="move", card_ids=[mob.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[mob.id], kind="+1/+1", delta=1)
    act(s, "p2", type="create_token", player="p2", token={"name": "Pump", "type_line": "Token Creature — Bear",
                                                           "power": "5", "toughness": "5", "text": ""})
    scrapper = to_hand(s, "Gruul Scrapper")
    mana(s, G=4)
    cast(s, scrapper)
    assert on_field_names(s).count("Zombie") == 1
    assert s.state.cards[mob.id].zone == "p1:graveyard"  # (0/0 with no counters: it dies, 704.5f)
    replay_matches(s)


# -- party (700.8) ------------------------------------------------------------------------------------------
def test_party_size_counts_each_creature_once_the_best_way(cards):
    """A Cleric Wizard and a Rogue Warrior are a party of two (each fills one place, 700.8b); an opponent's Warrior
    and a noncreature Rogue don't count. Malakir Blood-Priest (a Cleric) enters: the Cleric Wizard becomes the Wizard
    (the highest count, 700.8b), so X is 3."""
    from app.rules import values
    from app.rules.plan import Plan

    s = build(cards, "Malakir Blood-Priest")
    for pid, name, line in (("p1", "Sage", "Token Creature — Human Cleric Wizard"), ("p1", "Scout", "Token Creature — Elf Rogue Warrior"),
                            ("p2", "Theirs", "Token Creature — Human Warrior"), ("p1", "Cloak", "Token Artifact — Rogue")):
        act(s, pid, type="create_token", player=pid,
            token={"name": name, "type_line": line, "power": "1" if "Creature" in line else None,
                   "toughness": "1" if "Creature" in line else None, "text": ""})
    assert values.party_size(Plan.view(s.state, "p1", s.cards), "p1") == 2
    priest = to_hand(s, "Malakir Blood-Priest")
    mana(s, B=2)
    cast(s, priest)
    assert (life(s, "p1"), life(s, "p2")) == (43, 37)
    assert conditions.parse("you have a full party") == {"value": {"party": "you"}, "op": ">=", "n": 4}
    replay_matches(s)


# -- an ability the object has (109.3, 608.2h) -----------------------------------------------------------
def test_if_that_creature_has_a_keyword(cards):
    """Hexgold Slash: 4 damage to a creature with toxic (instead of 2); Burn the Impure: 3 more to the controller of a
    creature with infect; a creature without the keyword takes the plain damage."""
    s = build(cards, "Hexgold Slash", "Hexgold Slash", "Burn the Impure")
    one, two = [c for c in s.state.cards.values() if c.name == "Hexgold Slash"]
    burn = to_hand(s, "Burn the Impure")
    for c in (one, two):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    for name, text in (("Toxic", "Toxic 1"), ("Plain", ""), ("Infected", "Infect")):
        act(s, "p2", type="create_token", player="p2", token={"name": name, "type_line": "Token Creature — Phyrexian",
                                                               "power": "1", "toughness": "3", "text": text})
    toxic, plain, infected = named(s, "Toxic", "p2"), named(s, "Plain", "p2"), named(s, "Infected", "p2")
    mana(s, R=1)
    cast(s, one, targets=[toxic.id])
    assert "Toxic" not in on_field_names(s, "p2")  # (4 damage: it died)
    mana(s, R=1)
    cast(s, two, targets=[plain.id])
    assert s.state.cards[plain.id].damage == 2
    mana(s, R=2)
    cast(s, burn, targets=[infected.id])
    assert life(s, "p2") == 37
    replay_matches(s)


# -- reflexive triggered abilities: "When you do, …" (603.12) ------------------------------------------------
def answer(s, pick):
    """Answer the open decision with the option ``pick(decision)`` returns (a list of option ids)."""
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))


@pytest.mark.parametrize("pay", [True, False])
def test_reflexive_after_an_optional_cost(cards, pay):
    """Cavalier of Night: as its trigger resolves Alice may sacrifice another creature (118.12); only if she does
    does the reflexive ability trigger — its target is chosen as it goes on the stack afterwards (603.12, 603.3d)."""
    s = build(cards, "Cavalier of Night")
    fodder, bear = _creature(s, "p1", "Fodder"), _creature(s, "p2", "Bear")
    cavalier = to_hand(s, "Cavalier of Night")
    mana(s, B=5)
    act(s, "p1", type="cast_spell", card_id=cavalier.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} >= {"pay", "decline"}:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert not any(e.name == "Cavalier of Night" and e.targets for e in s.state.rules.stack.values())
    answer(s, lambda d: ["pay" if pay else "decline"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is not None:
            ids = [o.id for o in d.options]
            answer(s, lambda d, ids=ids: [bear.id] if bear.id in ids else [fodder.id] if fodder.id in ids else ids[:max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert ("Bear" in on_field_names(s, "p2")) is not pay
    assert ("Fodder" in on_field_names(s)) is not pay
    replay_matches(s)


def test_reflexive_after_a_mandatory_instruction(cards):
    """Brokers Hideout: "sacrifice it. When you do, search …" — sacrificed, the reflexive ability finds a basic
    Forest (tapped) and you gain 1 life."""
    s = build(cards, "Brokers Hideout")
    hideout = to_hand(s, "Brokers Hideout")
    act(s, "p1", type="play_land", card_id=hideout.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            break
        if d is not None:
            answer(s, lambda d: [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[hideout.id].zone == "p1:graveyard"
    forests = [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]
    assert len(forests) == 1 and s.state.cards[forests[0]].tapped
    assert life(s) == 41
    replay_matches(s)


def test_reflexive_modal_modes_are_chosen_after_the_payment(cards):
    """Caesar, Legion's Emperor: "you may sacrifice another creature. When you do, choose two —". The modes and their
    target are announced as the reflexive ability goes on the stack (603.3c), after the sacrifice — Alice picks the
    draw mode and the damage mode; Caesar deals damage equal to her creature tokens (one: the attacker) to Bob."""
    s = build(cards, "Caesar, Legion's Emperor")
    caesar = next(c for c in s.state.cards.values() if c.name == "Caesar, Legion's Emperor")
    act(s, "p1", type="move", card_ids=[caesar.id], to={"player": "p1", "zone": "battlefield"})
    fodder = _creature(s, "p1", "Fodder")
    raider = _creature(s, "p1", "Raider")
    until_turn(s, 3)
    hand = len(s.state.zones["p1:hand"])
    seen: list[str] = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": raider.id, "target": "p2"}])
            continue
        if d is None:
            if s.state.turn.phase in ("end", "cleanup") or (s.state.turn.phase == "main2" and not s.state.zones.get("stack")):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        seen.append(d.kind)
        ids = [o.id for o in d.options]
        if "pay" in ids:
            assert s.state.rules.pending_triggers == [] and not any(e.modes for e in s.state.rules.stack.values())
            answer(s, lambda d: ["pay"])
        elif fodder.id in ids:
            answer(s, lambda d: [fodder.id])
        elif any("You draw a card" in o.label for o in d.options):
            assert d.player == "p1" and d.max_choices == 2 and d.min_choices == 2
            answer(s, lambda d: [o.id for o in d.options if "You draw" in o.label or "Caesar deals" in o.label])
        elif "p2" in ids:
            answer(s, lambda d: ["p2"])
        else:
            answer(s, lambda d: [o.id for o in d.options][: max(1, d.min_choices)])
    assert "Fodder" not in on_field_names(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and life(s) == 39
    assert life(s, "p2") == 40 - 1 - 2  # (Caesar's 1 damage, then Raider's combat damage)
    replay_matches(s)


# -- modal headers that were refused (700.2) ---------------------------------------------------------------
def test_choose_one_at_random(cards):
    """Cult of Skaro: as its attack trigger goes on the stack one mode is picked at random among those that can be
    chosen — no one is asked — and announced (public); exactly one of the four happens."""
    s = build(cards, "Cult of Skaro")
    cult = next(c for c in s.state.cards.values() if c.name == "Cult of Skaro")
    act(s, "p1", type="move", card_ids=[cult.id], to={"player": "p1", "zone": "battlefield"})
    until_turn(s, 3)
    hand, bob = len(s.state.zones["p1:hand"]), life(s, "p2")
    act(s, "p2", type="set_prefs", response="on")  # (so the stack can be looked at)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": cult.id, "target": "p2"}])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "choose_cards"  # (nobody chooses)
    entry = next(e for e in s.state.rules.stack.values() if e.name == "Cult of Skaro")
    assert len(entry.modes) == 1
    settle(s)
    happened = [s.state.cards[cult.id].counters.get("+1/+1", 0) == 1, len(s.state.zones["p1:hand"]) == hand + 2,
                "Dalek" in on_field_names(s), life(s, "p2") == bob - 4]
    assert happened.count(True) == 1 and happened.index(True) == entry.modes[0]
    replay_matches(s)


@pytest.mark.parametrize("delirium", [True, False])
def test_choose_both_instead(cards, delirium):
    """Prophetic Titan: with four card types in the graveyard as the trigger goes on the stack, both modes (exactly
    two); otherwise one."""
    s = build(cards, "Prophetic Titan", "Clockwork Servant", "Seed Spark")
    if delirium:  # artifact + creature (Clockwork Servant), instant (Seed Spark), land (Forest)
        for name in ("Clockwork Servant", "Seed Spark", "Forest"):
            c = next(c for c in s.state.cards.values() if c.name == name and c.zone == "p1:library")
            act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    titan = to_hand(s, "Prophetic Titan")
    mana(s, U=1, R=1, G=4)
    act(s, "p1", type="cast_spell", card_id=titan.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and any("deals 4 damage" in o.label for o in d.options):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == ((2, 2) if delirium else (1, 1))
    replay_matches(s)


def three_players(cards, *names):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_each_mode_must_target_a_different_player(cards):
    """Vindictive Lich with two opponents: at most two modes (one opponent each); the second mode's target can't be
    the player the first one targets."""
    s = three_players(cards, "Vindictive Lich")
    lich = next(c for c in s.state.cards.values() if c.name == "Vindictive Lich")
    act(s, "p1", type="move", card_ids=[lich.id], to={"player": "p1", "zone": "battlefield"})
    for pid in ("p2", "p3"):
        for c in [c for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:library"][:3]:
            act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, "p1", type="set_damage", card_ids=[lich.id], delta=1)
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and d.max_choices == 2
    answer(s, lambda d: [o.id for o in d.options if "discards" in o.label or "loses 5" in o.label])
    d = s.state.rules.decision
    assert sorted(o.id for o in d.options) == ["p2", "p3"]
    answer(s, lambda d: ["p2"])
    d = s.state.rules.decision
    assert d is None or [o.id for o in d.options] == ["p3"]
    if d is not None:
        answer(s, lambda d: ["p3"])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == 1 and life(s, "p3") == 35
    replay_matches(s)


@pytest.mark.parametrize("still_there", [True, False])
def test_academy_rector_exile_it_if_you_do(cards, still_there):
    """Academy Rector: "you may exile it. If you do, search …" — the exile is probed: with the card still in the
    graveyard it's exiled and an enchantment comes; if it left the graveyard first (a new object elsewhere, 400.7),
    nothing is exiled and there is no search."""
    s = build(cards, "Academy Rector", "Promise of Bunrei")
    rector = next(c for c in s.state.cards.values() if c.name == "Academy Rector")
    act(s, "p1", type="move", card_ids=[rector.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_damage", card_ids=[rector.id], delta=2)
    act(s, "p1", type="pass_priority")
    for _ in range(5):
        if s.state.rules.stack:
            break
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1]) if d else None
    assert s.state.cards[rector.id].zone == "p1:graveyard"
    if not still_there:
        act(s, "p1", type="move", card_ids=[rector.id], to={"zone": "hand"})
    prompts = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        prompts.append(d.kind)
        pick = ["yes"] if d.kind == "confirm" else [o.id for o in d.options if "Promise" in (o.label or "")] or \
            [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    assert ("Promise of Bunrei" in on_field_names(s)) is still_there
    assert s.state.cards[rector.id].zone == ("p1:exile" if still_there else "p1:hand")
    replay_matches(s)


# -- "instead" and "other" (608.2c, 614.6) -------------------------------------------------------------
@pytest.mark.parametrize(("name", "where"), [("Gruul Scrapper", "library"), ("Ardenvale Paladin", "hand")])
def test_instead_pronoun_names_the_target(cards, name, where):
    """Consign to Dream: a green permanent (Gruul Scrapper) goes on top of its owner's library instead of to the
    hand — "it" is the target (the return never happened, 614.6); a white one (Ardenvale Paladin) is returned to the
    hand."""
    s = build(cards, "Consign to Dream", p2=["Gruul Scrapper", "Ardenvale Paladin"])
    victim = named(s, name, "p2")
    act(s, "p2", type="move", card_ids=[victim.id], to={"player": "p2", "zone": "battlefield"})
    consign = to_hand(s, "Consign to Dream")
    mana(s, U=3)
    cast(s, consign, targets=[victim.id])
    assert s.state.cards[victim.id].zone == f"p2:{where}"
    if where == "library":
        assert s.state.zones["p2:library"][0] == victim.id
    replay_matches(s)


@pytest.mark.parametrize(("x", "left"), [(5, 5), (2, 4)])
def test_martial_coup_other_than_the_tokens(cards, x, left):
    """Martial Coup: with X 5 or more every creature but the Soldiers it made is destroyed (other than the tokens,
    not the spell); with less, nothing is."""
    s = build(cards, "Martial Coup")
    _creature(s, "p1", "Mine")
    _creature(s, "p2", "Theirs")
    coup = to_hand(s, "Martial Coup")
    mana(s, W=2 + x)
    cast(s, coup, x_value=x)
    creatures = on_field_names(s) + on_field_names(s, "p2")
    assert creatures.count("Soldier") == x
    assert len(creatures) == left
    replay_matches(s)
