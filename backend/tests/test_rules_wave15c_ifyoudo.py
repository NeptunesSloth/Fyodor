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
    card('Genesis Wave', set_code='tst', number='W12', mana_cost='{X}{G}{G}{G}', cmc=3.0, type_line='Sorcery',
         oracle_text="Reveal the top X cards of your library. You may put any number of permanent cards with mana value X or less from among them onto the battlefield. Then put all cards revealed this way that weren't put onto the battlefield into your graveyard.", power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Elven Farsight', set_code='tst', number='W13', mana_cost='{G}', cmc=1.0, type_line='Sorcery',
         oracle_text='Scry 3, then you may reveal the top card of your library. If a creature card is revealed this way, draw a card.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=['Scry']),
    card('Armored Kincaller', set_code='tst', number='W14', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Dinosaur',
         oracle_text='When this creature enters, you may reveal a Dinosaur card from your hand. If you do or if you control another Dinosaur, you gain 3 life.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),
    card('Priest of the Wakening Sun', set_code='tst', number='W15', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Cleric',
         oracle_text='At the beginning of your upkeep, you may reveal a Dinosaur card from your hand. If you do, you gain 2 life.\n{3}{W}{W}, Sacrifice this creature: Search your library for a Dinosaur card, reveal it, put it into your hand, then shuffle.', power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=[]),
    card('Crypt Incursion', set_code='tst', number='W16', mana_cost='{2}{B}', cmc=3.0, type_line='Instant',
         oracle_text="Exile all creature cards from target player's graveyard. You gain 3 life for each card exiled this way.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Nightsnare', set_code='tst', number='W17', mana_cost='{3}{B}', cmc=4.0, type_line='Sorcery',
         oracle_text="Target opponent reveals their hand. You may choose a nonland card from it. If you do, that player discards that card. If you don't, that player discards two cards.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Oildeep Gearhulk', set_code='tst', number='W18', mana_cost='{U}{U}{B}{B}', cmc=4.0, type_line='Artifact Creature — Construct',
         oracle_text="Lifelink, ward {1}\nWhen this creature enters, look at target player's hand. You may choose a card from it. If you do, that player discards that card, then draws a card.", power='4', toughness='4', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Lifelink', 'Ward']),
    card('Wall of Resurgence', set_code='tst', number='W19', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Wall',
         oracle_text="Defender\nWhen this creature enters, you may put three +1/+1 counters on target land you control. If you do, that land becomes a 0/0 Elemental creature with haste that's still a land.", power='0', toughness='6', colors=['W'], color_identity=['W'], keywords=['Defender']),
    card('Nicol Bolas, the Deceiver', set_code='tst', number='W20', mana_cost='{5}{U}{B}{R}', cmc=8.0, type_line='Legendary Planeswalker — Bolas',
         oracle_text='+3: Each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.\n−3: Destroy target creature. Draw a card.\n−11: Nicol Bolas deals 7 damage to each opponent. You draw seven cards.', power=None, toughness=None, colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=[]),
    card('Torment of Scarabs', set_code='tst', number='W21', mana_cost='{3}{B}', cmc=4.0, type_line='Enchantment — Aura Curse',
         oracle_text="Enchant player\nAt the beginning of enchanted player's upkeep, that player loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=['Enchant']),
]
FULL = ['Murk Strider', 'Dark Supplicant', 'Gate to the Afterlife', 'Scion of Darkness', 'Void Attendant', 'Ruin Processor', 'Processor Assault', 'Wrexial, the Risen Deep', 'Deluxe Dragster', 'Zombie Cannibal', 'Fire Nation Salvagers', 'Traumatize', 'Genesis Wave', 'Elven Farsight', 'Armored Kincaller', 'Priest of the Wakening Sun', 'Crypt Incursion', 'Nightsnare', 'Oildeep Gearhulk', 'Wall of Resurgence', 'Nicol Bolas, the Deceiver', 'Torment of Scarabs']
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
    assert up is not None and up[0][0]["n"]["round"] == "up"
    s = build(cards, p1=("Traumatize",))
    spell = to_hand(s, "Traumatize")
    add_mana(s, "p1", U=2, C=3)
    before = len(zone(s.state, "p2", "library"))
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    assert len(zone(s.state, "p2", "library")) == before - before // 2
    assert len(zone(s.state, "p2", "graveyard")) == before // 2
    roundtrip(s)


def test_genesis_wave_sends_the_unchosen_revealed_cards_to_the_graveyard(cards):
    """Genesis Wave: the revealed cards that weren't put onto the battlefield go to the graveyard."""
    s = build(cards, p1=("Genesis Wave",))
    spell = to_hand(s, "Genesis Wave")
    top = list(zone(s.state, "p1", "library")[:3])
    add_mana(s, "p1", G=3, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3)
    d = until_asked(s)
    assert d is not None and d.kind == "choose_cards" and {o.id for o in d.options} == set(top)
    pick(s, top[0])
    settle(s)
    assert top[0] in zone(s.state, "p1", "battlefield")
    assert top[1] in zone(s.state, "p1", "graveyard") and top[2] in zone(s.state, "p1", "graveyard")
    roundtrip(s)


@pytest.mark.parametrize("reveal", [True, False])
def test_elven_farsight_reveal_is_optional_and_a_revealed_creature_draws(cards, reveal):
    s = build(cards, p1=("Elven Farsight", "Murk Strider"))
    spell = to_hand(s, "Elven Farsight")
    strider = find(s, "Murk Strider")
    act(s, "p1", type="move", card_ids=[strider.id], to={"player": "p1", "zone": "library"}, index=0)
    add_mana(s, "p1", G=1)
    hand_before = len(zone(s.state, "p1", "hand")) - 1  # (the spell leaves it)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    seen = []
    for _ in range(12):
        d = until_asked(s)
        if d is None:
            break
        seen.append(d.kind)
        if d.kind == "confirm":
            assert [o.id for o in d.options] == ["yes", "no"] and "options" not in s.view("p2")["rules"]["decision"]
            pick(s, "yes" if reveal else "no")
        else:  # the scry: leave the cards where they are
            pick(s, *[o.id for o in d.options][: d.min_choices])
    assert "confirm" in seen
    assert len(zone(s.state, "p1", "hand")) == hand_before + (1 if reveal else 0)  # 701.20a, 608.2c
    roundtrip(s)


@pytest.mark.parametrize(("hand_copy", "answer", "other_dino", "gain"), [
    (True, "pay", False, 3), (True, "decline", False, 0), (True, "decline", True, 3), (False, None, False, 0), (False, None, True, 3)])
def test_armored_kincaller_reveal_a_dinosaur_or_control_another(cards, hand_copy, answer, other_dino, gain):
    """"You may reveal a Dinosaur card from your hand. If you do or if you control another Dinosaur, you gain 3 life.":
    the reveal is a cost offered only while a Dinosaur card is in hand (118.3); the gain follows the payment or the other
    Dinosaur, either one (608.2c)."""
    s = build(cards, p1=("Armored Kincaller", "Armored Kincaller"))
    if other_dino:
        creature(s, "p1", "Raptor", "2/2", type_line="Token Creature — Dinosaur")
    copies = [c for c in s.state.cards.values() if c.name == "Armored Kincaller" and c.owner == "p1"]
    kincaller = to_zone(s, copies[0], "hand")
    if hand_copy:
        to_zone(s, copies[1], "hand")
    before = s.state.players["p1"].life
    add_mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=kincaller.id)
    for _ in range(6):
        if s.state.cards[kincaller.id].zone.endswith(":battlefield"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = until_asked(s)
    if answer is None:
        assert d is None
    else:
        assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
        pick(s, answer)
    settle(s)
    assert s.state.players["p1"].life == before + gain
    roundtrip(s)


def test_crypt_incursion_exiles_only_the_creature_cards_and_gains_for_each(cards):
    s = build(cards, p1=("Crypt Incursion",), p2=("Scion of Darkness", "Scion of Darkness", "Murk Strider"))
    spell = to_hand(s, "Crypt Incursion")
    scions = [c for c in s.state.cards.values() if c.name == "Scion of Darkness" and c.owner == "p2"]
    for c in scions:
        to_zone(s, c, "graveyard")
    island = to_zone(s, find(s, "Island", "p2"), "graveyard")  # a land card: stays
    mine = to_zone(s, find(s, "Forest"), "graveyard")
    before = s.state.players["p1"].life
    add_mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    assert all(c.id in zone(s.state, "p2", "exile") for c in scions) and island.id in zone(s.state, "p2", "graveyard")
    assert mine.id in zone(s.state, "p1", "graveyard")
    assert s.state.players["p1"].life == before + 6  # 3 life for each card exiled this way
    roundtrip(s)


@pytest.mark.parametrize("choose", [True, False])
def test_nightsnare_may_choose_a_card_and_if_not_the_opponent_discards_two(cards, choose):
    """"You may choose a nonland card from it. If you do, that player discards that card. If you don't, that player discards
    two cards." (608.2c: the second and third sentences read whether a card was chosen)"""
    s = build(cards, p1=("Nightsnare",), p2=("Murk Strider", "Dark Supplicant"))
    spell = to_hand(s, "Nightsnare")
    mine, spare = to_zone(s, find(s, "Murk Strider", "p2"), "hand"), to_zone(s, find(s, "Dark Supplicant", "p2"), "hand")
    for c in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:2]:
        to_zone(s, c, "hand")
    add_mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and d.min_choices == 0
    assert {o.id for o in d.options} == {mine.id, spare.id}  # nonland cards only
    pick(s, *([mine.id] if choose else []))
    if not choose:  # "that player discards two cards": their own choice
        d = until_asked(s)
        assert d is not None and d.player == "p2"
        pick(s, *[o.id for o in d.options][:2], pid="p2")
    settle(s)
    gy = zone(s.state, "p2", "graveyard")
    assert (len(gy) == 1 and mine.id in gy) if choose else len(gy) == 2
    roundtrip(s)


@pytest.mark.parametrize("paid", [True, False])
def test_wall_of_resurgence_land_becomes_a_creature_only_if_the_counters_went_on(cards, paid):
    """"You may put three +1/+1 counters on target land you control. If you do, that land becomes a 0/0 Elemental creature
    with haste that's still a land." (608.2c: "if you do" is whether the counters really were put on)"""
    from app.rules.plan import Plan

    s = build(cards, p1=("Wall of Resurgence",))
    forest = to_zone(s, find(s, "Forest"), "battlefield")
    enter(s, "Wall of Resurgence")
    d = until_asked(s)
    if d is not None and d.kind == "choose_one" and "pay" not in [o.id for o in d.options]:
        pick(s, forest.id)  # (the trigger's target, if it is asked)
        d = until_asked(s)
    if d is not None:
        pick(s, "yes" if paid else "no")
    settle(s)
    now = s.state.cards[forest.id]
    types = Plan(s.state, "p1", s.cards, None).ch(now).types
    assert (now.counters.get("+1/+1", 0) == 3) is paid and ("Creature" in types) is paid and "Land" in types
    roundtrip(s)


@pytest.mark.parametrize("pays", [True, False])
def test_nicol_bolas_each_opponent_loses_life_unless_they_sacrifice_or_discard(cards, pays):
    """"Each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card."
    (118.12a: each opponent may pay one of the two costs, in turn order; the others lose the life)"""
    s = build(cards, p1=("Nicol Bolas, the Deceiver",))
    bolas = to_zone(s, find(s, "Nicol Bolas, the Deceiver"), "battlefield")
    to_zone(s, find(s, "Island", "p2"), "hand")
    act(s, "p1", type="activate_ability", card_id=bolas.id, ability=0)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and "decline" in [o.id for o in d.options]
    assert "options" not in s.view("p1")["rules"]["decision"]  # (their choice is private to them)
    discard = [o.id for o in d.options if o.id != "decline"]
    assert len(discard) == 1  # (no nonland permanent to sacrifice: only the discard is offered, 118.3)
    pick(s, discard[0] if pays else "decline")
    settle(s)
    assert s.state.players["p2"].life == (40 if pays else 37)
    assert len(zone(s.state, "p2", "graveyard")) == (1 if pays else 0)
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
