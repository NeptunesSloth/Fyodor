"""Wave 6F: third pass on "If you do" (CR 2026-09-25).

* "You may blight N. If you do, …" (Sourbread Auntie, Dream Seizer, Boggart Mischief; "If you don't" — Gutsplitter
  Gang): a cost paid as the ability resolves (118.12); to blight N is to put N -1/-1 counters on one creature you
  control (701.68a); with no creature the option isn't offered (701.68b).
* "You may discard your hand / all the cards in your hand. If you do, draw that many cards / …" (Forgotten Creation,
  Narset, Jeskai Waymaster): every card in the hand (701.9a); it may be chosen with an empty hand (Wizards rulings on
  Narset, Jeskai Waymaster 2025-04-04 and Jackdaw 2024-07-05), and "that many" is the number discarded.
* "You may sacrifice an artifact or discard a card. If you do, …" (Vision of Love, K'un-Lun Warrior): either cost,
  each offered only while payable in full (118.3).
* "{T}, Remove any number of storage counters from this land: Add {C} for each storage counter removed this way."
  (storage lands, Mana Batteries): the number is chosen as the cost is paid (107.1c, 601.2h, 605.3a).
* "If you do, choose a color, then … of that color" (Rith, Dromar): the color is chosen as the instruction is reached.
* "create a … token, then attach this Equipment to it" (Dwarven Hammer, Ancestral Blade): 701.3a-b.

Real Commander cards, their Oracle text transcribed from the card database. Every scenario checks that replaying the
recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, mana, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, pick, settle, to_hand, until, until_asked
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_effects import replay_matches

EXTRA = [
    card('Sourbread Auntie', set_code='tst', number='F1', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Creature — Goblin Warrior',
         oracle_text='When this creature enters, you may blight 2. If you do, create two 1/1 black and red Goblin creature tokens. (To blight 2, put two -1/-1 counters on a creature you control.)', power='4', toughness='3', colors=['R'], color_identity=['R'], keywords=['Blight']),
    card('Gutsplitter Gang', set_code='tst', number='F2', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Goblin Berserker',
         oracle_text="At the beginning of your first main phase, you may blight 2. If you don't, you lose 3 life. (To blight 2, put two -1/-1 counters on a creature you control.)", power='6', toughness='6', colors=['B'], color_identity=['B'], keywords=['Blight']),
    card('Mage-Ring Network', set_code='tst', number='F3', mana_cost='', cmc=0.0, type_line='Land',
         oracle_text='{T}: Add {C}.\n{1}, {T}: Put a storage counter on this land.\n{T}, Remove any number of storage counters from this land: Add {C} for each storage counter removed this way.', colors=[], color_identity=[], keywords=[]),
    card('Blue Mana Battery', set_code='tst', number='F4', mana_cost='{4}', cmc=4.0, type_line='Artifact',
         oracle_text='{2}, {T}: Put a charge counter on this artifact.\n{T}, Remove any number of charge counters from this artifact: Add {U}, then add an additional {U} for each charge counter removed this way.', colors=[], color_identity=['U'], keywords=[]),
    card('Forgotten Creation', set_code='tst', number='F5', mana_cost='{3}{U}', cmc=4.0, type_line='Creature — Zombie Horror',
         oracle_text="Skulk (This creature can't be blocked by creatures with greater power.)\nAt the beginning of your upkeep, you may discard all the cards in your hand. If you do, draw that many cards.", power='3', toughness='3', colors=['U'], color_identity=['U'], keywords=['Skulk']),
    card('Narset, Jeskai Waymaster', set_code='tst', number='F6', mana_cost='{U}{R}{W}', cmc=3.0, type_line='Legendary Creature — Human Monk',
         oracle_text="At the beginning of your end step, you may discard your hand. If you do, draw cards equal to the number of spells you've cast this turn.", power='3', toughness='4', colors=['R', 'U', 'W'], color_identity=['R', 'U', 'W'], keywords=[]),
    card('Vision of Love', set_code='tst', number='F7', mana_cost='{1}{R}', cmc=2.0, type_line='Instant',
         oracle_text='You may sacrifice an artifact or discard a card. If you do, draw two cards.', colors=['R'], color_identity=['R'], keywords=[]),
    card("K'un-Lun Warrior", set_code='tst', number='F8', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Warrior Hero',
         oracle_text='When this creature enters, you may sacrifice an artifact or discard a card. If you do, draw a card.', power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),
    card('Dromar, the Banisher', set_code='tst', number='F9', mana_cost='{3}{W}{U}{B}', cmc=6.0, type_line='Legendary Creature — Dragon',
         oracle_text="Flying\nWhenever Dromar deals combat damage to a player, you may pay {2}{U}. If you do, choose a color, then return all creatures of that color to their owners' hands.", power='6', toughness='6', colors=['B', 'U', 'W'], color_identity=['B', 'U', 'W'], keywords=['Flying']),
    card('Rith, the Awakener', set_code='tst', number='F10', mana_cost='{3}{R}{G}{W}', cmc=6.0, type_line='Legendary Creature — Dragon',
         oracle_text='Flying\nWhenever Rith deals combat damage to a player, you may pay {2}{G}. If you do, choose a color, then create a 1/1 green Saproling creature token for each permanent of that color.', power='6', toughness='6', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W'], keywords=['Flying']),
    card('Dwarven Hammer', set_code='tst', number='F11', mana_cost='{2}{R}', cmc=3.0, type_line='Artifact — Equipment',
         oracle_text='When this Equipment enters, you may pay {2}. If you do, create a 2/1 red Dwarf Berserker creature token, then attach this Equipment to it.\nEquipped creature gets +3/+0 and has trample.\nEquip {3}', colors=['R'], color_identity=['R'], keywords=['Equip']),
    card('Ancestral Blade', set_code='tst', number='F12', mana_cost='{1}{W}', cmc=2.0, type_line='Artifact — Equipment',
         oracle_text='When this Equipment enters, create a 1/1 white Soldier creature token, then attach this Equipment to it.\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)', colors=['W'], color_identity=['W'], keywords=['Equip']),
    card('Dream Seizer', set_code='tst', number='F13', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Faerie Rogue',
         oracle_text='Flying\nWhen this creature enters, you may blight 1. If you do, each opponent discards a card. (To blight 1, put a -1/-1 counter on a creature you control.)', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Blight', 'Flying']),
    card('Boggart Mischief', set_code='tst', number='F14', mana_cost='{2}{B}', cmc=3.0, type_line='Kindred Enchantment — Goblin',
         oracle_text='When this enchantment enters, you may blight 1. If you do, create two 1/1 black and red Goblin creature tokens. (To blight 1, put a -1/-1 counter on a creature you control.)\nWhenever a Goblin creature you control dies, each opponent loses 1 life and you gain 1 life.', colors=['B'], color_identity=['B'], keywords=['Blight']),
    card('Book Devourer', set_code='tst', number='F15', mana_cost='{5}{R}', cmc=6.0, type_line='Creature — Beast',
         oracle_text='Trample\nWhenever this creature deals combat damage to a player, you may discard all the cards in your hand. If you do, draw that many cards.', power='4', toughness='5', colors=['R'], color_identity=['R'], keywords=['Trample']),
    card('Braids, Arisen Nightmare', set_code='tst', number='F17', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Legendary Creature — Nightmare',
         oracle_text="At the beginning of your end step, you may sacrifice an artifact, creature, enchantment, land, or planeswalker. If you do, each opponent may sacrifice a permanent of their choice that shares a card type with it. For each opponent who doesn't, that player loses 2 life and you draw a card.", power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=[]),
    card('Fandaniel, Telophoroi Ascian', set_code='tst', number='F18', mana_cost='{4}{B}', cmc=5.0, type_line='Legendary Creature — Elder Wizard',
         oracle_text="Whenever you cast an instant or sorcery spell, surveil 1.\nAt the beginning of your end step, each opponent may sacrifice a nontoken creature of their choice. Each opponent who doesn't loses 2 life for each instant and sorcery card in your graveyard.", power='4', toughness='5', colors=['B'], color_identity=['B'], keywords=['Surveil']),
    card('Impulsive Destruction', set_code='tst', number='F19', mana_cost='', cmc=0.0, type_line='Sorcery',
         oracle_text="Each player may sacrifice an artifact or enchantment. Impulsive Destruction deals 3 damage to each player who didn't sacrifice a permanent this way.", colors=[], color_identity=[], keywords=[]),
    card('Fire Prophecy', set_code='tst', number='F20', mana_cost='{1}{R}', cmc=2.0, type_line='Instant',
         oracle_text='Fire Prophecy deals 3 damage to target creature. You may put a card from your hand on the bottom of your library. If you do, draw a card.', colors=['R'], color_identity=['R'], keywords=[]),
    card('Sol Ring', set_code='tst', number='F16', mana_cost='{1}', cmc=1.0, type_line='Artifact',
         oracle_text='{T}: Add {C}{C}.', colors=[], color_identity=[], keywords=[]),
]
FULL = ["Sourbread Auntie", "Gutsplitter Gang", "Mage-Ring Network", "Blue Mana Battery", "Forgotten Creation",
        "Narset, Jeskai Waymaster", "Vision of Love", "K'un-Lun Warrior", "Dromar, the Banisher", "Rith, the Awakener",
        "Dwarven Hammer", "Ancestral Blade", "Dream Seizer", "Boggart Mischief", "Book Devourer", "Braids, Arisen Nightmare",
        "Fandaniel, Telophoroi Ascian", "Impulsive Destruction", "Fire Prophecy"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def enter(s, name, pid="p1", **extra):
    """Cast the permanent spell (its mana added first) and let it resolve: it enters, and its "enters" trigger is put on
    the stack."""
    import re

    c = to_hand(s, name, pid)
    cost = s.state.cards[c.id].name and next(x for x in EXTRA if x["name"] == name)["mana_cost"]
    pool: dict[str, int] = dict(extra)  # (and mana for its trigger's payment)
    for sym in re.findall(r"\{([^}]+)\}", cost):
        key = "C" if sym.isdigit() else sym
        pool[key] = pool.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    if pool:
        add_mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id)
    for _ in range(10):
        if s.state.cards[c.id].zone.endswith(":battlefield"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return c


def deal(s, pid, n, name):
    """Put ``n`` of the player's ``name`` cards from their library into their hand."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})


def hand(s, pid="p1"):
    return zone(s.state, pid, "hand")


def field_names(s, pid="p1"):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, "battlefield"))


def counters(s, c, kind="-1/-1"):
    return s.state.cards[c.id].counters.get(kind, 0)


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_wordings():
    found = scripts.parse_effects("You may blight 2. If you do, create a Treasure token.")
    assert found is not None and found[0][0] == {"do": "optional_payment", "who": "you", "cost": "Blight 2", "bind": "pay0"}
    found = scripts.parse_effects("You may discard all the cards in your hand. If you do, draw that many cards.")
    assert found is not None and found[0][-1]["n"] == {"paid_x": "pay0"}
    found = scripts.parse_effects("You may sacrifice an artifact or discard a card. If you do, draw two cards.")
    assert found is not None and found[0][0]["alts"] == ["Sacrifice an artifact", "Discard a card"]
    ring = mana.parse_mana_ability("{T}, Remove any number of storage counters from this land: Add {C} for each storage counter removed this way.")
    assert ring is not None and ring.count == "removed:storage:0"
    battery = mana.parse_mana_ability("{T}, Remove any number of charge counters from this artifact: Add {U}, then add an additional {U} for each charge counter removed this way.")
    assert battery is not None and battery.count == "removed:charge:1"


def test_refused_forms():
    # "that many" after declining, or a count of another kind of counter: not read
    assert scripts.parse_effects("You may discard your hand. If you don't, draw that many cards.") is None
    assert mana.parse_mana_ability("{T}, Remove any number of storage counters from this land: Add {C} for each charge counter removed this way.") is None
    assert mana.parse_mana_ability("{T}, Remove any number of charge counters from this artifact: Add {U}, then add an additional {R} for each charge counter removed this way.") is None
    # the mandatory "Discard your hand. If you do" stays refused (4A); only the optional form has the rulings
    assert scripts.parse_effects("Discard your hand. If you do, draw three cards.") is None


# -- blight -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("paid", [True, False])
def test_sourbread_auntie_blights_itself(cards, paid):
    s = build(cards, p1=("Sourbread Auntie",))
    auntie = enter(s, "Sourbread Auntie")
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]
    pick(s, "pay" if paid else "decline")
    settle(s)
    assert counters(s, auntie) == (2 if paid else 0)  # (the only creature: no choice to make)
    assert field_names(s).count("Goblin") == (2 if paid else 0)
    roundtrip(s)


def test_blight_chooses_one_creature_for_all_the_counters(cards):
    s = build(cards, p1=("Sourbread Auntie",))
    bear = creature(s, "p1", "Bear", "3/3")
    auntie = enter(s, "Sourbread Auntie")
    until_asked(s)
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.min_choices == d.max_choices == 1
    assert {o.id for o in d.options} == {bear.id, auntie.id}
    pick(s, bear.id)
    settle(s)
    assert counters(s, bear) == 2 and counters(s, auntie) == 0  # 701.68a: all on one creature
    assert field_names(s).count("Goblin") == 2
    roundtrip(s)


def test_blight_is_not_offered_without_a_creature(cards):
    """701.68b: Boggart Mischief with no creature: no blight, no Goblins."""
    s = build(cards, p1=("Boggart Mischief",))
    enter(s, "Boggart Mischief")
    assert until_asked(s) is None
    settle(s)
    assert "Goblin" not in field_names(s)
    roundtrip(s)


def test_dream_seizer_each_opponent_discards(cards):
    s = build(cards, p1=("Dream Seizer",))
    deal(s, "p2", 2, "Island")
    seizer = enter(s, "Dream Seizer")
    bob_hand = len(hand(s, "p2"))
    until_asked(s)
    pick(s, "pay")
    settle(s)
    assert counters(s, seizer) == 1
    assert len(hand(s, "p2")) == bob_hand - 1
    roundtrip(s)


# -- discard your hand --------------------------------------------------------------------------------
def _upkeep_trigger(s):
    until(s, lambda s: s.state.rules.decision is not None and [o.id for o in s.state.rules.decision.options] == ["pay", "decline"])


def test_forgotten_creation_draws_as_many_as_it_discarded(cards):
    s = build(cards, p1=("Forgotten Creation",))
    on_field(s, "Forgotten Creation")
    deal(s, "p1", 2, "Forest")
    _upkeep_trigger(s)
    assert s.state.rules.decision.player == "p1"
    before = list(hand(s))
    assert len(before) == 2
    pick(s, "pay")
    settle(s)
    # every card discarded, as many drawn — and then the draw step's card
    assert len(hand(s)) == 3 and not set(hand(s)) & set(before)
    assert all(s.state.cards[c].zone == "p1:graveyard" for c in before)
    roundtrip(s)


def test_forgotten_creation_with_an_empty_hand(cards):
    """Wizards rulings (Narset, Jeskai Waymaster; Jackdaw): the hand may be discarded with no card in it — none drawn."""
    s = build(cards, p1=("Forgotten Creation",))
    on_field(s, "Forgotten Creation")
    _upkeep_trigger(s)
    assert hand(s) == []
    library = len(zone(s.state, "p1", "library"))
    pick(s, "pay")
    settle(s)
    assert len(hand(s)) == 1 and len(zone(s.state, "p1", "library")) == library - 1  # (only the draw step's card)
    roundtrip(s)


def test_narset_with_an_empty_hand_still_draws(cards):
    """"If you do" checks the choice to pay (118.12): an empty hand discarded is the cost paid."""
    s = build(cards, p1=("Narset, Jeskai Waymaster", "Lightning Bolt"))
    on_field(s, "Narset, Jeskai Waymaster")
    bolt = to_hand(s, "Lightning Bolt")
    add_mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    for c in list(hand(s)):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    _upkeep_trigger(s)  # (her end step)
    pick(s, "pay")
    settle(s)
    assert len(hand(s)) == 1  # one spell cast this turn
    roundtrip(s)


# -- one cost or the other --------------------------------------------------------------------------
def test_vision_of_love_either_cost(cards):
    s = build(cards, p1=("Vision of Love", "Sol Ring"))
    ring = on_field(s, "Sol Ring")
    deal(s, "p1", 1, "Forest")
    spell = to_hand(s, "Vision of Love")
    add_mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and [o.id for o in d.options] == ["pay:0", "pay:1", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]
    pick(s, "pay:0")
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    roundtrip(s)


def test_vision_of_love_discards_when_no_artifact(cards):
    s = build(cards, p1=("Vision of Love",))
    deal(s, "p1", 2, "Forest")
    spell = to_hand(s, "Vision of Love")
    add_mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    before = len(hand(s))
    d = until_asked(s)
    assert [o.id for o in d.options] == ["pay:1", "decline"]  # (no artifact: 118.3)
    pick(s, "pay:1")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p1"
    assert "options" not in s.view("p2")["rules"]["decision"]  # (her hand: hidden)
    pick(s, d.options[0].id)
    settle(s)
    assert len(hand(s)) == before - 1 + 2
    roundtrip(s)


def test_kun_lun_warrior_declined(cards):
    s = build(cards, p1=("K'un-Lun Warrior",))
    deal(s, "p1", 1, "Forest")
    enter(s, "K'un-Lun Warrior")
    before = len(hand(s))
    d = until_asked(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    pick(s, "decline")
    settle(s)
    assert len(hand(s)) == before
    roundtrip(s)


# -- storage counters ---------------------------------------------------------------------------------
def test_mage_ring_network_removes_the_counters_it_adds_mana_for(cards):
    s = build(cards, p1=("Mage-Ring Network",))
    net = on_field(s, "Mage-Ring Network")
    act(s, "p1", type="counter", card_ids=[net.id], kind="storage", delta=3)
    act(s, "p1", type="activate_ability", card_id=net.id, ability=2)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == ["{C}", "{C}{C}", "{C}{C}{C}"]
    pick(s, d.options[1].id)
    assert s.state.players["p1"].mana.get("C", 0) == 2
    assert s.state.cards[net.id].counters.get("storage", 0) == 1 and s.state.cards[net.id].tapped
    roundtrip(s)


def test_mage_ring_network_with_no_counters(cards):
    s = build(cards, p1=("Mage-Ring Network",))
    net = on_field(s, "Mage-Ring Network")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=net.id, ability=2)
    assert not s.state.cards[net.id].tapped


def test_mana_battery_may_remove_none(cards):
    s = build(cards, p1=("Blue Mana Battery",))
    bat = on_field(s, "Blue Mana Battery")
    act(s, "p1", type="counter", card_ids=[bat.id], kind="charge", delta=2)
    act(s, "p1", type="activate_ability", card_id=bat.id, ability=1)
    d = s.state.rules.decision
    assert [o.label for o in d.options] == ["{U}", "{U}{U}", "{U}{U}{U}"]
    pick(s, d.options[0].id)
    assert s.state.players["p1"].mana.get("U", 0) == 1 and s.state.cards[bat.id].counters.get("charge", 0) == 2
    roundtrip(s)


def test_storage_mana_is_never_tapped_by_the_auto_payer(cards):
    s = build(cards, p1=("Mage-Ring Network", "Lightning Bolt"))
    net = on_field(s, "Mage-Ring Network")
    act(s, "p1", type="counter", card_ids=[net.id], kind="storage", delta=3)
    from app.rules import casting
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    sources = casting.mana_sources(s.state, "p1", plan.info)
    found = [src for src in sources if src.card_id == net.id]
    assert all(2 not in src.abilities for src in found)  # (its first ability, "{T}: Add {C}", may be)


# -- choose a color, then … ---------------------------------------------------------------------------
def _combat_damage(s, attacker, lands=("Forest", "Forest", "Forest")):
    for land in lands:
        c = next(c for c in s.state.cards.values() if c.name == land and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and [o.id for o in d.options][:2] == ["pay", "decline"]:
            return d
        elif d is not None:
            pick(s, d.options[0].id)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no payment asked")


def test_rith_counts_permanents_of_the_chosen_color(cards):
    s = build(cards, p1=("Rith, the Awakener",))
    rith = on_field(s, "Rith, the Awakener")
    creature(s, "p2", "Red Thing", "1/1")
    d = _combat_damage(s, rith)
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one" and "White" in [o.id for o in d.options]
    pick(s, "White")  # Rith is red, green and white: one white permanent
    settle(s)
    assert field_names(s).count("Saproling") == 1
    roundtrip(s)


def test_dromar_declined_chooses_nothing(cards):
    s = build(cards, p1=("Dromar, the Banisher", "Island"))
    dromar = on_field(s, "Dromar, the Banisher")
    _combat_damage(s, dromar, lands=("Forest", "Forest", "Island"))
    pick(s, "decline")
    settle(s)
    assert s.state.cards[dromar.id].zone == "p1:battlefield"
    roundtrip(s)


# -- create a token, then attach this Equipment to it ------------------------------------------------
@pytest.mark.parametrize("paid", [True, False])
def test_dwarven_hammer_attaches_to_its_token(cards, paid):
    s = build(cards, p1=("Dwarven Hammer",))
    hammer = enter(s, "Dwarven Hammer", C=2)
    until_asked(s)
    pick(s, "pay" if paid else "decline")
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.name == "Dwarf Berserker"]
    assert len(tokens) == (1 if paid else 0)
    assert s.state.cards[hammer.id].attached_to == (tokens[0].id if paid else None)
    roundtrip(s)


def test_ancestral_blade_attaches_to_its_soldier(cards):
    s = build(cards, p1=("Ancestral Blade",))
    blade = enter(s, "Ancestral Blade")
    settle(s)
    soldier = next(c for c in s.state.cards.values() if c.name == "Soldier")
    assert s.state.cards[blade.id].attached_to == soldier.id
    roundtrip(s)


# -- each opponent may … each opponent who doesn't … ---------------------------------------------------
def _asked(s, pid):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == pid
          and [o.id for o in s.state.rules.decision.options] == ["pay", "decline"])
    return s.state.rules.decision


@pytest.mark.parametrize("bob_pays", [True, False])
def test_braids_each_opponent_may_sacrifice_a_permanent_sharing_a_type(cards, bob_pays):
    s = build(cards, p1=("Braids, Arisen Nightmare",))
    braids = on_field(s, "Braids, Arisen Nightmare")
    bear = creature(s, "p1", "Bear")
    wolf = creature(s, "p2", "Wolf")
    _asked(s, "p1")
    pick(s, "pay")
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and {o.id for o in d.options} == {braids.id, bear.id}
    pick(s, bear.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p1")["rules"]["decision"]  # (Bob's choice, privately)
    bob, cards_in_hand = life(s, "p2"), len(hand(s))
    pick(s, "pay" if bob_pays else "decline")
    settle(s)
    assert (wolf.id in s.state.cards and s.state.cards[wolf.id].zone.endswith("battlefield")) == (not bob_pays)
    assert life(s, "p2") == bob - (0 if bob_pays else 2)
    assert len(hand(s)) == cards_in_hand + (0 if bob_pays else 1)
    roundtrip(s)


def test_braids_an_opponent_with_nothing_sharing_a_type_is_not_asked(cards):
    """118.3: Bob controls no creature, so he can't pay — he loses 2 life and Alice draws."""
    s = build(cards, p1=("Braids, Arisen Nightmare",))
    on_field(s, "Braids, Arisen Nightmare")
    bear = creature(s, "p1", "Bear")
    act(s, "p2", type="move", card_ids=[next(c for c in zone(s.state, "p2", "library"))], to={"player": "p2", "zone": "battlefield"})
    _asked(s, "p1")
    bob, cards_in_hand = life(s, "p2"), len(hand(s))
    pick(s, "pay")
    pick(s, bear.id)
    assert s.state.rules.decision is None or s.state.rules.decision.player != "p2"
    settle(s)
    assert life(s, "p2") == bob - 2 and len(hand(s)) == cards_in_hand + 1
    roundtrip(s)


def test_braids_declined_nothing_happens(cards):
    s = build(cards, p1=("Braids, Arisen Nightmare",))
    on_field(s, "Braids, Arisen Nightmare")
    creature(s, "p2", "Wolf")
    bob = life(s, "p2")
    _asked(s, "p1")
    pick(s, "decline")
    settle(s)
    assert life(s, "p2") == bob
    roundtrip(s)


def test_fandaniel_each_opponent_who_doesnt(cards):
    s = build(cards, p1=("Fandaniel, Telophoroi Ascian", "Lightning Bolt"))
    on_field(s, "Fandaniel, Telophoroi Ascian")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "graveyard"})
    bob = life(s, "p2")
    creature(s, "p2", "Wolf")  # (a token: not a nontoken creature — Bob can't pay)
    until(s, lambda s: s.state.turn.number == 2)
    settle(s)
    assert life(s, "p2") == bob - 2  # one instant in Alice's graveyard
    roundtrip(s)


def test_impulsive_destruction_each_player_in_turn_order(cards):
    s = build(cards, p1=("Impulsive Destruction", "Sol Ring"), p2=("Sol Ring",))
    on_field(s, "Sol Ring")
    on_field(s, "Sol Ring", "p2")
    spell = to_hand(s, "Impulsive Destruction")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d.player == "p1"  # 101.4: the active player first
    pick(s, "decline")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    pick(s, "pay")
    settle(s)
    assert life(s, "p1") == 37 and life(s, "p2") == 40
    roundtrip(s)


# -- a card from your hand on the bottom of your library ------------------------------------------------
def test_fire_prophecy_bottoms_a_card_privately_then_draws(cards):
    import json

    s = build(cards, p1=("Fire Prophecy", "Sol Ring"))
    bear = creature(s, "p2", "Bear")
    ring = to_hand(s, "Sol Ring")
    deal(s, "p1", 1, "Forest")
    spell = to_hand(s, "Fire Prophecy")
    add_mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    d = until_asked(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "pay")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p1"
    assert "options" not in s.view("p2")["rules"]["decision"]
    pick(s, ring.id)
    settle(s)
    assert zone(s.state, "p1", "library")[-1] == ring.id  # (its bottom)
    assert len(hand(s)) == 2  # the Forest and the card drawn
    assert bear.id not in zone(s.state, "p2", "battlefield")
    assert "Sol Ring" not in json.dumps(s.view("p2"))  # (never revealed: 400.2)
    roundtrip(s)


def test_fire_prophecy_with_an_empty_hand_is_not_offered(cards):
    s = build(cards, p1=("Fire Prophecy",))
    bear = creature(s, "p2", "Bear")
    spell = to_hand(s, "Fire Prophecy")
    add_mana(s, "p1", R=1, C=1)
    library = len(zone(s.state, "p1", "library"))
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    assert until_asked(s) is None  # (her hand is empty — public: its size may be counted, 402.3)
    assert len(zone(s.state, "p1", "library")) == library and hand(s) == []
    roundtrip(s)
