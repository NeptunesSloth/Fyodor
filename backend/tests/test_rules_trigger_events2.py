"""More trigger events, matched against what actually happened (CR 2026-09-25): the Nth spell each
turn and spells that target (601.2i, 115.9b), sacrifices (701.21a, 603.10a), discards and cycling
(701.9a, 702.29c-d), tokens created (111.2), counters put on (122.6), cards leaving a graveyard
(603.10a), attacks alone / with N creatures / battalion (506.5, 508.1m, 508.3d), blocks (509.3a-d),
becoming a target (115.1, 603.2e), dealing damage (120.1, 120.4b) — plus a trigger's delayed
resolution: its source leaving, other spells resolving first."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import events
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import resolve_all, responsive, stack_entry, wait_for

EXTRA = [
    card("Test Cycler", set_code="tst", number="TE1", mana_cost="{3}{B}", cmc=4.0, type_line="Creature — Horror",
         oracle_text="Cycling {B} ({B}, Discard this card: Draw a card.)\nWhen you cycle this card, you gain 3 life.",
         power="3", toughness="3", colors=["B"], color_identity=["B"]),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def life(s, pid="p1"):
    return s.state.players[pid].life


def activate(s, card, **kw):
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card.id, ability=0, **kw)
    resolve_all(s)


# -- parsing ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(("cond", "event", "extra"), [
    ("you cast your second spell each turn", "cast", {"nth": 2}),
    ("you cast your first spell during each opponent's turn", "cast", {"nth": 1, "turn": "opponent"}),
    ("you cast a spell that targets ~", "cast", {"targets": "self"}),
    ("you cast a spell from exile", "cast", {"from": "exile"}),
    ("you sacrifice a creature", "sacrifice", {"player": "you"}),
    ("you sacrifice ~", "sacrifice", {"subject": "self"}),
    ("an opponent discards a card", "discard", {"player": "opponent"}),
    ("you cycle or discard a card", "discard", {"player": "you"}),  # 702.29d: once for a cycled card
    ("you cycle ~", "cycle", {"subject": "self"}),
    ("you create one or more tokens", "create_token", {"aggregate": True}),
    ("one or more +1/+1 counters are put on ~", "counters_put", {"counter": "+1/+1"}),
    ("one or more creature cards leave your graveyard", "leave_graveyard", {"aggregate": True}),
    ("~ attacks alone", "attack", {"alone": True}),
    ("~ and at least two other creatures attack", "attack", {"min_attackers": 3}),
    ("you attack with three or more creatures", "you_attack", {"min_attackers": 3}),
    ("~ attacks or blocks", "multi", {"events": ["attack", "block"]}),
    ("~ becomes blocked by a creature", "blocked", {"subject": "self"}),
    ("~ becomes the target of a spell or ability an opponent controls", "targeted", {"by": "opponent"}),
    ("~ deals combat damage to a creature", "deal_damage", {"to": "creature", "combat": True}),
    ("enchanted creature attacks", "attack", {"subject": "host"}),
    ("one or more tokens you control enter", "enter", {"aggregate": True}),
])
def test_parse_more_conditions(cond, event, extra):
    got = events.parse_condition(cond)
    assert got is not None and got["event"] == event, cond
    assert {k: got.get(k) for k in extra} == extra, got


@pytest.mark.parametrize("cond", [
    "you cast your second spell",  # (no "each turn")
    "you sacrifice two creatures",
    "you create a Goblin",  # (not a token phrase)
])
def test_more_unknown_conditions_stay_manual(cond):
    assert events.parse_condition(cond) is None


# -- spells: the Nth each turn, targets (601.2i, 115.9b) --------------------------------------------
def test_second_spell_each_turn(cards):
    s = build(cards, "Lightning Bolt", "Giant Growth")
    token(s, "p1", "Sage", "2/2", text="Whenever you cast your second spell each turn, you gain 2 life.")
    bear = token(s, "p1", "Bear", "2/2")
    bolt, growth = to_hand(s, "Lightning Bolt"), to_hand(s, "Giant Growth")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve_all(s)
    assert life(s) == 40
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    resolve_all(s)
    assert life(s) == 42
    replay_matches(s)


def test_heroic_triggers_only_for_a_spell_that_targets_it(cards):
    s = build(cards, "Lightning Bolt", "Giant Growth")
    hero = token(s, "p1", "Hero", "1/1", text="Whenever you cast a spell that targets this creature, "
                                              "put a +1/+1 counter on this creature.")
    bolt, growth = to_hand(s, "Lightning Bolt"), to_hand(s, "Giant Growth")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve_all(s)
    assert not s.state.cards[hero.id].counters
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[hero.id])
    resolve_all(s)
    assert s.state.cards[hero.id].counters == {"+1/+1": 1}
    replay_matches(s)


# -- sacrifice (701.21a; 603.10a: looks back in time) -----------------------------------------------
@pytest.mark.parametrize("victim_text", [
    "{1}: Sacrifice this creature.",  # an effect
    "{1}, Sacrifice this creature: You gain 0 life.",  # a cost
])
def test_whenever_you_sacrifice_a_creature(cards, victim_text):
    s = build(cards)
    token(s, "p1", "Priest", "2/2", text="Whenever you sacrifice a creature, each opponent loses 1 life.")
    victim = token(s, "p1", "Victim", "1/1", text=victim_text)
    activate(s, victim)
    assert life(s, "p2") == 39
    replay_matches(s)


def test_dying_is_not_sacrificing(cards):
    s = build(cards)
    token(s, "p1", "Priest", "5/5", text="Whenever you sacrifice a creature, each opponent loses 1 life.")
    token(s, "p1", "Sprout", "1/1")
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.")
    activate(s, src)
    assert life(s, "p2") == 40


def test_when_you_sacrifice_this_creature(cards):
    s = build(cards)
    hand = len(zone(s.state, "p1", "hand"))
    victim = token(s, "p1", "Ordeal", "1/1", text="{1}: Sacrifice this creature.\nWhen you sacrifice this creature, draw a card.")
    activate(s, victim)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


# -- discard and cycling (701.9a, 702.29) -----------------------------------------------------------
def test_opponent_discards_that_player_loses_life(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)
    token(s, "p1", "Tormentor", "2/2", text="Whenever an opponent discards a card, that player loses 2 life.")
    src = token(s, "p1", "Mind Rot", text="{1}: Each opponent discards a card.")
    activate(s, src)
    assert life(s, "p2") == 38 and life(s) == 40
    replay_matches(s)


def test_cycling_triggers_cycle_or_discard_once_and_its_own_ability(cards):
    s = build(cards, "Test Cycler", "Swamp")
    swamp = named(s, "Swamp")
    act(s, "p1", type="move", card_ids=[swamp.id], to={"zone": "battlefield"})
    cycler = to_hand(s, "Test Cycler")
    token(s, "p1", "Sniper", "2/2", text="Whenever you cycle or discard a card, each opponent loses 1 life.")
    act(s, "p1", type="activate_ability", card_id=cycler.id, ability=0)  # Cycling {B}
    resolve_all(s)
    assert s.state.cards[cycler.id].zone == "p1:graveyard"
    assert life(s, "p2") == 39  # 702.29d: once
    assert life(s) == 43  # 702.29c: "When you cycle this card" triggers from the graveyard
    replay_matches(s)


# -- tokens, counters, graveyards ------------------------------------------------------------------
def test_create_one_or_more_tokens_once_per_event(cards):
    s = build(cards)
    token(s, "p1", "Mayor", "2/2", text="Whenever you create one or more tokens, you gain 1 life.")
    src = token(s, "p1", "Muster", text="{1}: Create two 1/1 white Soldier creature tokens.")
    activate(s, src)
    assert life(s) == 41
    replay_matches(s)


def test_counters_put_on_this_creature(cards):
    s = build(cards)
    grower = token(s, "p1", "Grower", "1/1", text="{1}: Put two +1/+1 counters on this creature.\n"
                                                  "Whenever one or more +1/+1 counters are put on this creature, you gain 1 life.")
    activate(s, grower)
    assert s.state.cards[grower.id].counters == {"+1/+1": 2} and life(s) == 41
    replay_matches(s)


def test_creature_card_leaves_your_graveyard(cards):
    s = build(cards, "Llanowar Elves")
    elf = named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "graveyard"})
    token(s, "p1", "Keeper", "2/2", text="Whenever a creature card leaves your graveyard, you gain 1 life.")
    src = token(s, "p1", "Raiser", text="{1}: Return target creature card from your graveyard to your hand.")
    activate(s, src, targets=[elf.id])
    assert s.state.cards[elf.id].zone == "p1:hand" and life(s) == 41
    replay_matches(s)


# -- combat ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(("n", "pumped"), [(1, True), (2, False)])
def test_attacks_alone(cards, n, pumped):
    s = table(cards)
    creature(s, "p1", "Captain", "1/1", text="Whenever a creature you control attacks alone, it gets +2/+2 until end of turn.")
    a = creature(s, "p1", "A")
    b = creature(s, "p1", "B")
    automate(s)
    attack(s, *[(x, "p2") for x in (a, b)[:n]])
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[a.id]).pt == ((4, 4) if pumped else (2, 2))
    replay_matches(s)


@pytest.mark.parametrize(("text", "gain"), [
    ("Whenever this creature and at least two other creatures attack, you gain 1 life.", 1),
    ("Whenever you attack with three or more creatures, you gain 1 life.", 1),
    ("Whenever you attack with four or more creatures, you gain 1 life.", 0),
    ("Whenever this creature attacks or blocks, you gain 1 life.", 1),
])
def test_attack_counts(cards, text, gain):
    s = table(cards)
    leader = creature(s, "p1", "Leader", "1/1", text=text)
    a = creature(s, "p1", "A")
    b = creature(s, "p1", "B")
    automate(s)
    attack(s, (leader, "p2"), (a, "p2"), (b, "p2"))
    pass_until_stack_empty(s)
    assert life(s) == 40 + gain, text
    replay_matches(s)


@pytest.mark.parametrize(("text", "gain"), [
    ("Whenever this creature becomes blocked by a creature, you gain 1 life.", 2),  # 509.3d: per blocker
    ("Whenever this creature becomes blocked, you gain 1 life.", 1),  # 509.3c: once
    ("Whenever this creature blocks or becomes blocked by a creature, you gain 1 life.", 2),
])
def test_blocked_by_each_creature(cards, text, gain):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "5/5", text=text)
    x = creature(s, "p2", "X", "1/1")
    y = creature(s, "p2", "Y", "1/1")
    automate(s)
    attack(s, (brute, "p2"))
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            block(s, "p2", (x, brute), (y, brute))
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert life(s) == 40 + gain, text
    replay_matches(s)


def test_blocks_a_creature(cards):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "1/1")
    wall = creature(s, "p2", "Wall", "0/4", text="Whenever this creature blocks a creature, you gain 2 life.")
    automate(s)
    attack(s, (brute, "p2"))
    for _ in range(4):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            block(s, "p2", (wall, brute))
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pass_until_stack_empty(s)
    assert life(s, "p2") == 42
    replay_matches(s)


# -- becoming a target; dealing damage ------------------------------------------------------------
def test_targeted_for_the_first_time_each_turn(cards):
    s = build(cards)
    hero = token(s, "p1", "Valiant", "2/2", text="Whenever this creature becomes the target of a spell or ability "
                                                  "you control for the first time each turn, you gain 1 life.")
    src = token(s, "p1", "Tapper", text="{1}: Untap target creature.")
    activate(s, src, targets=[hero.id])
    activate(s, src, targets=[hero.id])
    assert life(s) == 41
    replay_matches(s)


def test_deals_damage_once_for_several_recipients(cards):
    # one damage event to several creatures: "whenever ~ deals damage" triggers once, the amount summed
    s = build(cards)
    src = token(s, "p1", "Quake", "5/5", text="{1}: This creature deals 1 damage to each creature.\n"
                                              "Whenever this creature deals damage, you gain that much life.")
    token(s, "p1", "A", "3/3")
    token(s, "p2", "B", "3/3")
    activate(s, src)
    assert life(s) == 43  # A, B and itself: one trigger, 3 damage
    replay_matches(s)


# -- delayed resolution: what the trigger captured stays; its source may be gone -----------------
def test_trigger_resolves_after_its_source_left_and_another_spell_resolved(cards):
    s = build(cards, "Lightning Bolt")
    responsive(s)
    watcher = token(s, "p1", "Collector", "5/5", text="Whenever a creature you control dies, draw cards equal to its power.")
    victim = token(s, "p1", "Victim", "1/1", text="{1}: Sacrifice this creature.")
    act(s, "p1", type="counter", card_ids=[victim.id], kind="+1/+1", delta=1)  # 2/2 as it dies
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=victim.id, ability=0)
    entry = wait_for(s, "Collector")
    assert entry.event.objects[0].snapshot.power == 2  # last known information (608.2h)
    # the source leaves, and a spell cast in response resolves first
    act(s, "p1", type="move", card_ids=[watcher.id], to={"zone": "exile"})
    bolt = named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    mana(s, R=1)
    act(s, s.state.rules.priority, type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve_all(s)
    assert stack_entry(s, "Collector") is None
    assert life(s, "p2") == 37
    assert len(zone(s.state, "p1", "hand")) == hand + 2  # (Bolt came from the library: + 2 drawn)
    replay_matches(s)
