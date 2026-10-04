"""Wave 15C: long-tail "If you do" / "this way" wordings (CR 2026-09-25).

* "Put a card an opponent owns from exile into that player's graveyard" (the Eldrazi processors: Murk Strider, Void
  Attendant, Ruin Processor, Processor Assault …): a cost like any other (118.1) — paid as an activated ability's cost, as a
  spell's additional cost, or as the optional payment "you may … If you do, …" (118.12); the cards are chosen among the
  face-up cards in the opponents' exile zones (406.3) and go to their owners' graveyards (400.3).
* "Search your graveyard, hand, and/or library for a card named …" (Dark Supplicant, Gate to the Afterlife): the searcher
  chooses which of the zones to look through (701.23a); "If you search your library this way, shuffle" shuffles only when the
  library was one of them (701.24).
* "[A]. You may draw a card. If you do, discard a card." in the middle of an ability (Gate to the Afterlife's first ability):
  the player is asked once as the resolution reaches it (608.2d); "if you do" reads what the draw actually did (608.2c).

Real Commander cards, their Oracle text transcribed from the card database. Every scenario checks that replaying the
recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_effects import replay_matches

# --EXTRA-BEGIN--
EXTRA = [
    card('Murk Strider', set_code='tst', number='W0', mana_cost='{3}{U}', cmc=4.0, type_line='Creature — Eldrazi Processor',
         oracle_text="Devoid (This card has no color.)\nWhen this creature enters, you may put a card an opponent owns from exile into that player's graveyard. If you do, return target creature to its owner's hand.", power='3', toughness='2', colors=[], color_identity=['U'], keywords=['Devoid']),
    card('Dark Supplicant', set_code='tst', number='W1', mana_cost='{B}', cmc=1.0, type_line='Creature — Human Cleric',
         oracle_text='{T}, Sacrifice three Clerics: Search your graveyard, hand, and/or library for a card named Scion of Darkness and put it onto the battlefield. If you search your library this way, shuffle.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),
    card('Gate to the Afterlife', set_code='tst', number='W2', mana_cost='{3}', cmc=3.0, type_line='Artifact',
         oracle_text="Whenever a nontoken creature you control dies, you gain 1 life. Then you may draw a card. If you do, discard a card.\n{2}, {T}, Sacrifice this artifact: Search your graveyard, hand, and/or library for a card named God-Pharaoh's Gift and put it onto the battlefield. If you search your library this way, shuffle. Activate only if there are six or more creature cards in your graveyard.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Scion of Darkness', set_code='tst', number='W3', mana_cost='{5}{B}{B}{B}', cmc=8.0, type_line='Creature — Avatar',
         oracle_text="Trample\nWhenever this creature deals combat damage to a player, you may put target creature card from that player's graveyard onto the battlefield under your control.\nCycling {3} ({3}, Discard this card: Draw a card.)", power='6', toughness='6', colors=['B'], color_identity=['B'], keywords=['Trample', 'Cycling']),
    card('Void Attendant', set_code='tst', number='W4', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Eldrazi Processor',
         oracle_text='Devoid (This card has no color.)\n{1}{G}, Put a card an opponent owns from exile into that player\'s graveyard: Create a 1/1 colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add {C}."', power='2', toughness='3', colors=[], color_identity=['G'], keywords=['Devoid']),
    card('Ruin Processor', set_code='tst', number='W5', mana_cost='{7}', cmc=7.0, type_line='Creature — Eldrazi Processor',
         oracle_text="When you cast this spell, you may put a card an opponent owns from exile into that player's graveyard. If you do, you gain 5 life.", power='7', toughness='8', colors=[], color_identity=[], keywords=[]),
    card('Processor Assault', set_code='tst', number='W6', mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery',
         oracle_text="Devoid (This card has no color.)\nAs an additional cost to cast this spell, put a card an opponent owns from exile into that player's graveyard.\nProcessor Assault deals 5 damage to target creature.", power=None, toughness=None, colors=[], color_identity=['R'], keywords=['Devoid']),
    card('Wrexial, the Risen Deep', set_code='tst', number='W7', mana_cost='{3}{U}{U}{B}', cmc=6.0, type_line='Legendary Creature — Kraken',
         oracle_text="Islandwalk, swampwalk (This creature can't be blocked as long as defending player controls an Island or a Swamp.)\nWhenever Wrexial deals combat damage to a player, you may cast target instant or sorcery card from that player's graveyard without paying its mana cost. If that spell would be put into a graveyard, exile it instead.", power='5', toughness='8', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Landwalk', 'Swampwalk', 'Islandwalk']),
    card('Deluxe Dragster', set_code='tst', number='W8', mana_cost='{4}{U}', cmc=5.0, type_line='Artifact — Vehicle',
         oracle_text="This Vehicle can't be blocked except by Vehicles.\nWhenever this Vehicle deals combat damage to a player, you may cast target instant or sorcery card from that player's graveyard without paying its mana cost. If that spell would be put into a graveyard, exile it instead.\nCrew 2", power='4', toughness='3', colors=['U'], color_identity=['U'], keywords=['Crew']),
    card('Zombie Cannibal', set_code='tst', number='W9', mana_cost='{B}', cmc=1.0, type_line='Creature — Zombie',
         oracle_text="Whenever this creature deals combat damage to a player, you may exile target card from that player's graveyard.", power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),
    card('Fire Nation Salvagers', set_code='tst', number='W10', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Human Soldier',
         oracle_text="Menace\nWhen this creature enters, put a +1/+1 counter on target creature or Vehicle you control.\nWhenever one or more creatures you control with counters on them deal combat damage to a player, put target creature or Vehicle card from that player's graveyard onto the battlefield under your control.", power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Menace']),
    card('Traumatize', set_code='tst', number='W11', mana_cost='{3}{U}{U}', cmc=5.0, type_line='Sorcery',
         oracle_text='Target player mills half their library, rounded down.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Mill']),
]
FULL = ['Murk Strider', 'Dark Supplicant', 'Gate to the Afterlife', 'Scion of Darkness', 'Void Attendant', 'Ruin Processor', 'Processor Assault', 'Wrexial, the Risen Deep', 'Deluxe Dragster', 'Zombie Cannibal', 'Fire Nation Salvagers', 'Traumatize']
# --EXTRA-END--


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


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def field_names(s, pid="p1"):
    return sorted(s.state.cards[c].name for c in zone(s.state, pid, "battlefield"))


def to_zone(s, c, where, pid=None):
    act(s, pid or c.owner, type="move", card_ids=[c.id], to={"player": pid or c.owner, "zone": where})
    return c


def exile_from_library(s, pid):
    """The top card of the player's library, exiled (face up)."""
    cid = zone(s.state, pid, "library")[0]
    act(s, pid, type="move", card_ids=[cid], to={"zone": "exile"})
    return s.state.cards[cid]


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def enter(s, name, pid="p1"):
    """Cast the permanent spell (its mana added first) and let it resolve: it enters, and its "enters" trigger is put on
    the stack."""
    import re

    c = to_hand(s, name, pid)
    pool: dict[str, int] = {}
    for sym in re.findall(r"\{([^}]+)\}", next(x for x in EXTRA if x["name"] == name)["mana_cost"]):
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


@pytest.mark.parametrize("paid", [True, False])
def test_murk_strider_puts_an_exiled_card_into_its_owners_graveyard(cards, paid):
    s = build(cards, p1=("Murk Strider",))
    bear = creature(s, "p1", "Bear", "2/2")
    mine = to_zone(s, find(s, "Forest"), "exile")  # (my own exiled card: not an opponent's, never offered)
    theirs = exile_from_library(s, "p2")
    enter(s, "Murk Strider")
    pick(s, bear.id)  # the trigger's target, chosen as it is put on the stack (603.3d)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]
    roundtrip(s)  # a save taken while the payment is open
    pick(s, "pay" if paid else "decline")
    settle(s)
    assert (theirs.id in zone(s.state, "p2", "graveyard")) is paid  # 400.3: to its owner's graveyard
    assert (theirs.id in zone(s.state, "p2", "exile")) is not paid
    assert mine.id in zone(s.state, "p1", "exile")
    assert (bear.id not in zone(s.state, "p1", "battlefield")) is paid  # "If you do, return target creature to its owner's hand"
    roundtrip(s)


def test_void_attendant_and_processor_assault_pay_as_a_cost(cards):
    s = build(cards, p1=("Void Attendant", "Processor Assault"))
    attendant = to_zone(s, find(s, "Void Attendant"), "battlefield")
    victim = creature(s, "p2", "Victim", "3/3")
    a, b = exile_from_library(s, "p2"), exile_from_library(s, "p2")
    add_mana(s, "p1", G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=attendant.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and {o.id for o in d.options} == {a.id, b.id}  # (a cost: 601.2h)
    pick(s, a.id)
    settle(s)
    assert a.id in zone(s.state, "p2", "graveyard") and b.id in zone(s.state, "p2", "exile")
    assert "Eldrazi Scion" in field_names(s)
    roundtrip(s)
    assault = to_hand(s, "Processor Assault")
    add_mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=assault.id, targets=[victim.id], cost_choices=[{"component": 0, "cards": [b.id]}])
    settle(s)
    assert b.id in zone(s.state, "p2", "graveyard") and victim.id not in zone(s.state, "p2", "battlefield")  # 5 damage
    roundtrip(s)


@pytest.mark.parametrize("zones", ["hand", "library+hand+graveyard"])
def test_dark_supplicant_searches_the_hand_and_or_other_zones(cards, zones):
    s = build(cards, p1=("Dark Supplicant", "Scion of Darkness", "Scion of Darkness"))
    sup = to_zone(s, find(s, "Dark Supplicant"), "battlefield")
    clerics = [creature(s, "p1", f"Acolyte {i}", "1/1", type_line="Token Creature — Human Cleric") for i in range(2)]
    for c in (sup, *clerics):
        s.state.rules.controlled_since[c.id].turn = 0
    in_hand = to_hand(s, "Scion of Darkness")
    in_library = next(c for c in s.state.cards.values() if c.name == "Scion of Darkness" and c.zone == "p1:library")
    before = list(zone(s.state, "p1", "library"))
    act(s, "p1", type="activate_ability", card_id=sup.id, ability=0)
    settle_until = until_asked(s)
    assert settle_until is not None and settle_until.kind == "choose_one"
    assert {o.id for o in settle_until.options} >= {"hand", "library+hand+graveyard"}  # 701.23a: any of the zones named
    pick(s, zones)
    d = until_asked(s)
    assert d is not None and d.kind == "choose_cards"
    assert {o.id for o in d.options} == ({in_hand.id} if zones == "hand" else {in_hand.id, in_library.id})
    roundtrip(s)
    pick(s, in_hand.id)
    settle(s)
    assert in_hand.id in zone(s.state, "p1", "battlefield") and field_names(s).count("Scion of Darkness") == 1
    assert (list(zone(s.state, "p1", "library")) == before) is (zones == "hand")  # 701.24: shuffled only when searched
    assert "Acolyte 0" not in field_names(s) and sup.id not in zone(s.state, "p1", "battlefield")  # (sacrificed)
    roundtrip(s)


@pytest.mark.parametrize("draws", [True, False])
def test_gate_to_the_afterlife_gains_then_may_loot(cards, draws):
    s = build(cards, p1=("Gate to the Afterlife", "Dark Supplicant", "Lightning Bolt"))
    to_zone(s, find(s, "Gate to the Afterlife"), "battlefield")
    sup = to_zone(s, find(s, "Dark Supplicant"), "battlefield")
    bolt = to_hand(s, "Lightning Bolt")
    for forest in [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:2]:
        to_zone(s, forest, "hand")
    add_mana(s, "p1", R=1)
    before, hand_before = s.state.players["p1"].life, len(zone(s.state, "p1", "hand")) - 1
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[sup.id])  # a nontoken creature you control dies
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"  # 608.2d: asked once, after the life is gained
    assert s.state.players["p1"].life == before + 1
    pick(s, "yes" if draws else "no")
    if draws:
        d = until_asked(s)
        assert d is not None and d.kind == "choose_cards" and len(zone(s.state, "p1", "hand")) == hand_before + 1
        pick(s, d.options[0].id)  # "If you do, discard a card"
    settle(s)
    assert len(zone(s.state, "p1", "hand")) == hand_before
    assert len(zone(s.state, "p1", "graveyard")) == (3 if draws else 2)  # (Lightning Bolt, the Supplicant, the discard)
    roundtrip(s)


def test_scion_of_darkness_takes_a_creature_only_from_the_damaged_players_graveyard(cards):
    """"… target creature card from that player's graveyard": the player the trigger is about (608.2k), bound as it is put on the
    stack — a creature card in my own graveyard is not a legal target."""
    from app.game.rules_state import ControlMark
    from tests.test_rules_conditionals import attack, until

    s = build(cards, p1=("Scion of Darkness", "Scion of Darkness"), p2=("Scion of Darkness",))
    scion = to_zone(s, find(s, "Scion of Darkness"), "battlefield")
    s.state.rules.controlled_since[scion.id] = ControlMark(controller="p1", turn=0)
    mine = to_zone(s, next(c for c in s.state.cards.values() if c.name == "Scion of Darkness" and c.zone == "p1:library"), "graveyard")
    theirs = to_zone(s, find(s, "Scion of Darkness", "p2"), "graveyard")
    act(s, "p1", type="pass_priority")  # → combat
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    attack(s, (scion, "p2"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind in ("choose_one", "choose_cards"))
    d = s.state.rules.decision
    assert theirs.id in {o.id for o in d.options} and mine.id not in {o.id for o in d.options}
    pick(s, theirs.id)
    settle(s)
    assert theirs.id in zone(s.state, "p1", "battlefield") or any(
        c.name == "Scion of Darkness" and c.zone == "p1:battlefield" and c.id != scion.id for c in s.state.cards.values())
    assert mine.id in zone(s.state, "p1", "graveyard")
    roundtrip(s)


def test_traumatize_mills_half_the_library_rounded_down(cards):
    """"Target player mills half their library, rounded down." (107.1a: half of what is there when it resolves)"""
    from app.rules import scripts

    up = scripts.parse_effects("Target opponent mills half their library, rounded up.")
    assert up is not None and up[0][0]["half"] == "up"
    s = build(cards, p1=("Traumatize",))
    spell = to_hand(s, "Traumatize")
    add_mana(s, "p1", U=2, C=3)
    before = len(zone(s.state, "p2", "library"))
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    assert len(zone(s.state, "p2", "library")) == before - before // 2
    assert len(zone(s.state, "p2", "graveyard")) == before // 2
    roundtrip(s)


def test_murk_strider_cannot_pay_without_an_opponents_exiled_card(cards):
    s = build(cards, p1=("Murk Strider",))
    bear = creature(s, "p1", "Bear", "2/2")
    to_zone(s, find(s, "Forest"), "exile")
    enter(s, "Murk Strider")
    pick(s, bear.id)
    assert until_asked(s) is None  # 118.3: nothing to pay with, so the option isn't offered
    assert bear.id in zone(s.state, "p1", "battlefield")
    roundtrip(s)
