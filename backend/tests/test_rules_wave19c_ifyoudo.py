"""Wave 19C: long-tail "If you do" / "this way" wordings (CR 2026-09-25).

* State triggers about the permanent's own counters (603.8): "When Dark Depths has no ice counters on it, sacrifice it. If you
  do, create Marit Lage …" / "When there are four or more page counters on this artifact, exile it. If you do, you gain 4 life."
* "Once during each of your turns, you may cast an instant or sorcery spell from your graveyard. If a spell cast this way would be
  put into your graveyard, exile it instead." (Kess; 614.1a, a replacement of where the spell goes) and the typed form after a free
  cast ("If an instant or sorcery spell cast this way …": Scholar of the Lost Trove — a permanent spell is not replaced).
* "Draw a card, then discard a card. When you discard a nonland / creature card this way, …" (603.12 reflexive trigger, counting what
  the discard really moved: Evie Frye, Teo, Talion's Messenger).
* "Whenever you scry, … for each card looked at while scrying this way" (701.22d: fewer than N with a short library).
* "Each player discards a card. If you discarded a card this way, …" (the cards the controller discarded).

Real Commander cards, their Oracle text transcribed from the card database. Every scenario checks that replaying the recorded
history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import pick, settle, to_hand
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_effects import replay_matches

# --EXTRA-BEGIN--
EXTRA = [
    card('Dark Depths', set_code='tst', number='W0', mana_cost='', cmc=0.0, type_line='Legendary Snow Land',
         oracle_text='Dark Depths enters with ten ice counters on it.\n{3}: Remove an ice counter from Dark Depths.\nWhen Dark Depths has no ice counters on it, sacrifice it. If you do, create Marit Lage, a legendary 20/20 black Avatar creature token with flying and indestructible.', power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Mazemind Tome', set_code='tst', number='W1', mana_cost='{2}', cmc=2.0, type_line='Artifact — Book',
         oracle_text='{T}, Put a page counter on this artifact: Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{2}, {T}, Put a page counter on this artifact: Draw a card.\nWhen there are four or more page counters on this artifact, exile it. If you do, you gain 4 life.', power=None, toughness=None, colors=[], color_identity=[], keywords=['Scry']),
    card('Kess, Dissident Mage', set_code='tst', number='W2', mana_cost='{1}{U}{B}{R}', cmc=4.0, type_line='Legendary Creature — Human Wizard',
         oracle_text='Flying\nOnce during each of your turns, you may cast an instant or sorcery spell from your graveyard. If a spell cast this way would be put into your graveyard, exile it instead.', power='3', toughness='4', colors=['B', 'R', 'U'], color_identity=['B', 'R', 'U'], keywords=['Flying']),
    card('Scholar of the Lost Trove', set_code='tst', number='W3', mana_cost='{5}{U}{U}', cmc=7.0, type_line='Creature — Sphinx',
         oracle_text='Flying\nWhen this creature enters, you may cast target instant, sorcery, or artifact card from your graveyard without paying its mana cost. If an instant or sorcery spell cast this way would be put into your graveyard, exile it instead.', power='5', toughness='5', colors=['U'], color_identity=['U'], keywords=['Flying']),
    card('Evie Frye', set_code='tst', number='W4', mana_cost='{1}{U}', cmc=2.0, type_line='Legendary Creature — Human Assassin',
         oracle_text="Partner with Jacob Frye (When this creature enters, target player may put Jacob into their hand from their library, then shuffle.)\n{1}, {T}: Draw a card, then discard a card. When you discard a creature card this way, target creature you control can't be blocked this turn.", power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Partner with', 'Partner']),
    card('Teo, Spirited Glider', set_code='tst', number='W5', mana_cost='{3}{U}', cmc=4.0, type_line='Legendary Creature — Human Pilot Ally',
         oracle_text='Flying\nWhenever one or more creatures you control with flying attack, draw a card, then discard a card. When you discard a nonland card this way, put a +1/+1 counter on target creature you control.', power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=['Flying']),
    card('Celeborn the Wise', set_code='tst', number='W6', mana_cost='{3}{G}', cmc=4.0, type_line='Legendary Creature — Elf Noble',
         oracle_text='Whenever you attack with one or more Elves, scry 1.\nWhenever you scry, Celeborn gets +1/+1 until end of turn for each card looked at while scrying this way.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Scry']),
    card('Fanatic of the Harrowing', set_code='tst', number='W7', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Human Cleric',
         oracle_text='When this creature enters, each player discards a card. If you discarded a card this way, draw a card.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=[]),
    card("Talion's Messenger", set_code='tst', number='W8', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Faerie Noble',
         oracle_text='Flying\nWhenever you attack with one or more Faeries, draw a card, then discard a card. When you discard a card this way, put a +1/+1 counter on target Faerie you control.', power='1', toughness='3', colors=['U'], color_identity=['U'], keywords=['Flying']),
    card('Master of Death', set_code='tst', number='W20', mana_cost='{1}{U}{B}', cmc=3.0, type_line='Creature — Zombie Wizard',
         oracle_text='When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nAt the beginning of your upkeep, if this card is in your graveyard, you may pay 1 life. If you do, return it to your hand.', power='3', toughness='1', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Surveil']),
    card('Genesis', set_code='tst', number='W21', mana_cost='{4}{G}', cmc=5.0, type_line='Creature — Incarnation',
         oracle_text='At the beginning of your upkeep, if this creature is in your graveyard, you may pay {2}{G}. If you do, return target creature card from your graveyard to your hand.', power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=[]),
    card('Pyre Zombie', set_code='tst', number='W22', mana_cost='{1}{B}{R}', cmc=3.0, type_line='Creature — Zombie',
         oracle_text='At the beginning of your upkeep, if this card is in your graveyard, you may pay {1}{B}{B}. If you do, return it to your hand.\n{1}{R}{R}, Sacrifice this creature: It deals 2 damage to any target.', power='2', toughness='1', colors=['B', 'R'], color_identity=['B', 'R'], keywords=[]),
    card('Ghastly Remains', set_code='tst', number='W23', mana_cost='{B}{B}{B}', cmc=3.0, type_line='Creature — Zombie',
         oracle_text='Amplify 1 (As this creature enters, put a +1/+1 counter on it for each Zombie card you reveal in your hand.)\nAt the beginning of your upkeep, if this card is in your graveyard, you may pay {B}{B}{B}. If you do, return it to your hand.', power='0', toughness='0', colors=['B'], color_identity=['B'], keywords=['Amplify']),
    card('Overwhelming Forces', set_code='tst', number='W30', mana_cost='{6}{B}{B}', cmc=8.0, type_line='Sorcery',
         oracle_text='Destroy all creatures target opponent controls. Draw a card for each creature destroyed this way.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Rain of Daggers', set_code='tst', number='W31', mana_cost='{4}{B}{B}', cmc=6.0, type_line='Sorcery',
         oracle_text='Destroy all creatures target opponent controls. You lose 2 life for each creature destroyed this way.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Baral, Chief of Compliance', set_code='tst', number='W40', mana_cost='{1}{U}', cmc=2.0, type_line='Legendary Creature — Human Wizard',
         oracle_text='Instant and sorcery spells you cast cost {1} less to cast.\nWhenever a spell or ability you control counters a spell, you may draw a card. If you do, discard a card.', power='1', toughness='3', colors=['U'], color_identity=['U'], keywords=[]),
    card('Lullmage Mentor', set_code='tst', number='W41', mana_cost='{1}{U}{U}', cmc=3.0, type_line='Creature — Merfolk Wizard',
         oracle_text='Whenever a spell or ability you control counters a spell, you may create a 1/1 blue Merfolk creature token.\nTap seven untapped Merfolk you control: Counter target spell.', power='2', toughness='2', colors=['U'], color_identity=['U'], keywords=[]),
    card('Gigapede', set_code='tst', number='W50', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Insect',
         oracle_text="Shroud (This creature can't be the target of spells or abilities.)\nAt the beginning of your upkeep, if this card is in your graveyard, you may discard a card. If you do, return this card to your hand.", power='6', toughness='1', colors=['G'], color_identity=['G'], keywords=['Shroud']),
    card('Blood Operative', set_code='tst', number='W51', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Creature — Vampire Assassin',
         oracle_text='Lifelink\nWhen this creature enters, you may exile target card from a graveyard.\nWhenever you surveil, if this card is in your graveyard, you may pay 3 life. If you do, return this card to your hand.', power='3', toughness='1', colors=['B'], color_identity=['B'], keywords=['Lifelink']),
    card('Pyrewild Shaman', set_code='tst', number='W52', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Goblin Shaman',
         oracle_text='Bloodrush — {1}{R}, Discard this card: Target attacking creature gets +3/+1 until end of turn.\nWhenever one or more creatures you control deal combat damage to a player, if this card is in your graveyard, you may pay {3}. If you do, return this card to your hand.', power='3', toughness='1', colors=['R'], color_identity=['R'], keywords=['Bloodrush']),
    card('Ichorid', set_code='tst', number='W60', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Horror',
         oracle_text='Haste\nAt the beginning of the end step, sacrifice this creature.\nAt the beginning of your upkeep, if this card is in your graveyard, you may exile a black creature card other than this card from your graveyard. If you do, return this card to the battlefield.', power='3', toughness='1', colors=['B'], color_identity=['B'], keywords=['Haste']),
    card('Furious Forebear', set_code='tst', number='W70', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Spirit Warrior',
         oracle_text='Whenever a creature you control dies while this card is in your graveyard, you may pay {1}{W}. If you do, return this card from your graveyard to your hand.', power='3', toughness='1', colors=['W'], color_identity=['W'], keywords=[]),
    card('Boneyard Scourge', set_code='tst', number='W71', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Creature — Zombie Dragon',
         oracle_text='Flying\nWhenever a Dragon you control dies while this card is in your graveyard, you may pay {1}{B}. If you do, return this card from your graveyard to the battlefield.', power='4', toughness='3', colors=['B'], color_identity=['B'], keywords=['Flying']),
]
FULL = ['Dark Depths', 'Mazemind Tome', 'Kess, Dissident Mage', 'Scholar of the Lost Trove', 'Evie Frye', 'Teo, Spirited Glider', 'Celeborn the Wise', 'Fanatic of the Harrowing', "Talion's Messenger", 'Master of Death', 'Genesis', 'Pyre Zombie', 'Ghastly Remains', 'Overwhelming Forces', 'Rain of Daggers', 'Baral, Chief of Compliance', 'Lullmage Mentor', 'Gigapede', 'Blood Operative', 'Pyrewild Shaman', 'Ichorid', 'Furious Forebear', 'Boneyard Scourge']
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


def put_counters(s, c, kind, n):
    act(s, c.controller, type="counter", card_ids=[c.id], kind=kind, delta=n)


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_dark_depths_is_sacrificed_for_marit_lage_when_the_last_ice_counter_goes(cards):
    s = build(cards, p1=("Dark Depths",))
    depths = to_zone(s, find(s, "Dark Depths"), "hand")
    act(s, "p1", type="play_land", card_id=depths.id)
    settle(s)
    assert s.state.cards[depths.id].counters.get("ice") == 10  # (it enters with them: 122.6a)
    for n in range(10):
        assert "Marit Lage" not in field_names(s)  # (while a counter is left there is nothing to trigger on)
        add_mana(s, "p1", C=3)
        act(s, "p1", type="activate_ability", card_id=depths.id, ability=1)
        settle(s)
    assert field_names(s) == ["Marit Lage"]  # sacrificed, and "if you do" made the token
    marit = find(s, "Marit Lage")
    assert marit.is_token and (marit.token.power, marit.token.toughness) == ("20", "20")
    roundtrip(s)


def test_mazemind_tome_is_exiled_at_four_page_counters_and_gains_life(cards):
    s = build(cards, p1=("Mazemind Tome",))
    tome = to_zone(s, find(s, "Mazemind Tome"), "battlefield")
    life = s.state.players["p1"].life
    for n in range(4):
        assert tome.id in zone(s.state, "p1", "battlefield")  # (below four page counters nothing triggers)
        if s.state.cards[tome.id].tapped:
            act(s, "p1", type="tap", card_ids=[tome.id])  # (untapped by hand)
        act(s, "p1", type="activate_ability", card_id=tome.id, ability=0)  # {T}, put a page counter: scry 1
        settle(s)
    assert find(s, "Mazemind Tome").zone == "p1:exile" and s.state.players["p1"].life == life + 4  # exiled, "if you do": gain 4
    roundtrip(s)


def cast_from_graveyard(s, c, **kw):
    add_mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    settle(s)


def test_kess_casts_an_instant_from_the_graveyard_once_and_it_is_exiled_instead(cards):
    s = build(cards, p1=("Kess, Dissident Mage", "Lightning Bolt", "Lightning Bolt"))
    to_zone(s, find(s, "Kess, Dissident Mage"), "battlefield")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for b in bolts:
        to_zone(s, b, "graveyard")
    life = s.state.players["p2"].life
    cast_from_graveyard(s, bolts[0], targets=["p2"])
    assert s.state.players["p2"].life == life - 3
    assert s.state.cards[bolts[0].id].zone == "p1:exile"  # 614.1a: exiled instead of going to the graveyard
    add_mana(s, "p1", R=1)
    with pytest.raises(ActionError):  # once during each of your turns
        act(s, "p1", type="cast_spell", card_id=bolts[1].id, targets=["p2"])
    assert s.state.cards[bolts[1].id].zone == "p1:graveyard"
    roundtrip(s)


def play_out(s, prefer=(), limit=30):
    """Answer whatever is asked (the first of ``prefer`` that is on offer, else the first option) and let the stack resolve."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = next((p for p in prefer if p in ids), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen] if chosen else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_a_countered_kess_spell_is_exiled_too(cards):
    s = build(cards, p1=("Kess, Dissident Mage", "Lightning Bolt"), p2=("Counterspell",))
    to_zone(s, find(s, "Kess, Dissident Mage"), "battlefield")
    bolt = to_zone(s, find(s, "Lightning Bolt"), "graveyard")
    counter = to_zone(s, find(s, "Counterspell", "p2"), "hand")
    add_mana(s, "p1", R=1)
    add_mana(s, "p2", U=2)  # (Bob can answer, so he gets priority as the Bolt is cast)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bolt.id])
    play_out(s)
    assert s.state.players["p2"].life == 40  # countered
    assert s.state.cards[bolt.id].zone == "p1:exile"  # "would be put into your graveyard": exiled instead (614.1a)
    assert s.state.cards[counter.id].zone == "p2:graveyard"
    roundtrip(s)


def test_scholar_of_the_lost_trove_casts_an_instant_free_and_it_is_exiled(cards):
    s = build(cards, p1=("Scholar of the Lost Trove", "Lightning Bolt"))
    bolt = to_zone(s, find(s, "Lightning Bolt"), "graveyard")
    scholar = to_hand(s, "Scholar of the Lost Trove")
    add_mana(s, "p1", U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=scholar.id)
    play_out(s, prefer=("yes", bolt.id, "p2"))
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("discard", ["Llanowar Elves", "Forest"])
def test_evie_frye_gives_unblockable_only_for_a_creature_card_discarded(cards, discard):
    s = build(cards, p1=("Evie Frye", "Llanowar Elves"))
    evie = to_zone(s, find(s, "Evie Frye"), "battlefield")
    play_out(s)  # (her "partner with" trigger)
    s.state.rules.controlled_since[evie.id].turn = 0
    to_zone(s, find(s, "Llanowar Elves"), "hand")
    add_mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=evie.id, ability=1)  # draw a card (a Forest), then discard a card
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and "options" not in s.view("p2")["rules"]["decision"]
    keep = [o.id for o in d.options if o.label == discard]
    pick(s, *keep)
    d = s.state.rules.decision
    if discard == "Llanowar Elves":  # a creature card: the reflexive ability's target is chosen as it goes on the stack (603.3d)
        assert d is not None and d.kind == "choose_one"
        pick(s, evie.id)
    else:
        assert d is None  # a land: nothing triggers
    play_out(s)
    assert ("cant_be_blocked" in ch(s, evie).imposed) is (discard == "Llanowar Elves")
    roundtrip(s)


def test_celeborn_gets_a_counter_of_power_for_each_card_looked_at_while_scrying(cards):
    s = build(cards, p1=("Celeborn the Wise", "Mazemind Tome"))
    celeborn = to_zone(s, find(s, "Celeborn the Wise"), "battlefield")
    tome = to_zone(s, find(s, "Mazemind Tome"), "battlefield")
    base = ch(s, celeborn).pt
    act(s, "p1", type="activate_ability", card_id=tome.id, ability=0)  # scry 1: one card looked at
    play_out(s)
    assert ch(s, celeborn).pt == (base[0] + 1, base[1] + 1)
    roundtrip(s)
    # 701.22d: a scry with no cards in the library looks at none
    for c in list(zone(s.state, "p1", "library")):
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="tap", card_ids=[tome.id])
    now = ch(s, celeborn).pt
    act(s, "p1", type="activate_ability", card_id=tome.id, ability=0)
    play_out(s)
    assert ch(s, celeborn).pt == now
    roundtrip(s)


@pytest.mark.parametrize("hand", [["Llanowar Elves"], []])
def test_fanatic_of_the_harrowing_draws_only_if_you_discarded(cards, hand):
    s = build(cards, p1=("Fanatic of the Harrowing", "Llanowar Elves"), p2=("Counterspell",))
    for n in hand:
        to_zone(s, find(s, n), "hand")
    to_zone(s, find(s, "Counterspell", "p2"), "hand")
    fanatic = to_hand(s, "Fanatic of the Harrowing")
    add_mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=fanatic.id)
    play_out(s)
    assert [s.state.cards[c].name for c in zone(s.state, "p2", "graveyard")] == ["Counterspell"]  # every player discards
    assert len(zone(s.state, "p1", "hand")) == (1 if hand else 0)  # "If you discarded a card this way, draw a card"
    assert len(zone(s.state, "p1", "graveyard")) == len(hand)
    roundtrip(s)


def to_upkeep_choice(s):
    """Play on until the open decision is a pay / decline one."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} >= {"pay", "decline"}:
            return d
        if d is not None:  # (the cleanup discard to hand size, …: the first options)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no payment was offered")


@pytest.mark.parametrize("pay", [True, False])
def test_master_of_death_returns_from_the_graveyard_at_upkeep_for_a_life(cards, pay):
    s = build(cards, p1=("Master of Death",))
    master = to_zone(s, find(s, "Master of Death"), "graveyard")
    life = s.state.players["p1"].life
    d = to_upkeep_choice(s)
    assert d.player == "p1" and s.state.turn.number == 3 and s.state.cards[master.id].zone == "p1:graveyard"
    roundtrip(s)
    pick(s, "pay" if pay else "decline")
    play_out(s)
    assert (s.state.cards[master.id].zone == "p1:hand") is pay  # "If you do, return it to your hand"
    assert s.state.players["p1"].life == life - (1 if pay else 0)
    roundtrip(s)


def test_a_graveyard_trigger_does_not_work_from_the_battlefield(cards):
    """113.6: the "if this card is in your graveyard" ability functions only there; on the battlefield Master of Death asks nothing."""
    s = build(cards, p1=("Master of Death",))
    master = to_zone(s, find(s, "Master of Death"), "battlefield")
    play_out(s)  # (its surveil)
    life = s.state.players["p1"].life
    for _ in range(40):
        d = s.state.rules.decision
        assert d is None or not {o.id for o in d.options} >= {"pay", "decline"}
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.number == 3 and s.state.players["p1"].life == life and s.state.cards[master.id].zone == "p1:battlefield"
    roundtrip(s)


def token_creature(s, pid, name, text=""):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": "2",
                                                         "toughness": "2", "text": text})
    return find(s, name, pid)


@pytest.mark.parametrize("spell", ["Overwhelming Forces", "Rain of Daggers"])
def test_destroy_all_of_target_opponents_creatures_counts_only_the_ones_destroyed(cards, spell):
    s = build(cards, p1=(spell,))
    victims = [token_creature(s, "p2", f"Bear {i}") for i in range(2)]
    tough = token_creature(s, "p2", "Golem", "Indestructible")  # not destroyed (702.12b): not counted
    mine = token_creature(s, "p1", "Mine")
    card_ = to_hand(s, spell)
    life, hand = s.state.players["p1"].life, len(zone(s.state, "p1", "hand"))
    add_mana(s, "p1", B=2, C=6)
    act(s, "p1", type="cast_spell", card_id=card_.id, targets=["p2"])
    play_out(s)
    assert [c.id in zone(s.state, "p2", "battlefield") for c in (*victims, tough)] == [False, False, True]
    assert mine.id in zone(s.state, "p1", "battlefield")  # only the target opponent's creatures
    if spell == "Overwhelming Forces":
        assert len(zone(s.state, "p1", "hand")) == hand - 1 + 2  # (the spell left the hand) "a card for each creature destroyed"
    else:
        assert s.state.players["p1"].life == life - 4  # 2 life for each of the two destroyed
    roundtrip(s)


def test_baral_loots_when_a_spell_you_control_counters_a_spell(cards):
    s = build(cards, p1=("Llanowar Elves",), p2=("Baral, Chief of Compliance", "Counterspell"))
    to_zone(s, find(s, "Baral, Chief of Compliance", "p2"), "battlefield")
    counter = to_zone(s, find(s, "Counterspell", "p2"), "hand")
    elves = to_hand(s, "Llanowar Elves")
    add_mana(s, "p1", G=1)
    add_mana(s, "p2", U=2)
    library = len(zone(s.state, "p2", "library"))
    act(s, "p1", type="cast_spell", card_id=elves.id)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[elves.id])
    play_out(s, prefer=("yes",))
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    assert len(zone(s.state, "p2", "library")) == library - 1  # "you may draw a card. If you do, discard a card"
    assert len(zone(s.state, "p2", "graveyard")) == 2  # Counterspell and the discarded card
    roundtrip(s)


def test_baral_does_not_loot_for_a_spell_that_is_not_countered(cards):
    s = build(cards, p1=("Llanowar Elves",), p2=("Baral, Chief of Compliance", "Counterspell"))
    to_zone(s, find(s, "Baral, Chief of Compliance", "p2"), "battlefield")
    elves = to_hand(s, "Llanowar Elves")
    add_mana(s, "p1", G=1)
    library = len(zone(s.state, "p2", "library"))
    act(s, "p1", type="cast_spell", card_id=elves.id)
    play_out(s, prefer=("yes",))
    assert s.state.cards[elves.id].zone == "p1:battlefield" and len(zone(s.state, "p2", "library")) == library
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_blood_operative_returns_from_the_graveyard_when_you_surveil(cards, pay):
    """"Whenever you surveil, if this card is in your graveyard, you may pay 3 life. If you do, return this card to your hand."
    (the trigger works from the graveyard only; "this card" there is the one in the graveyard, 113.6)"""
    s = build(cards, p1=("Blood Operative", "Master of Death"))
    operative = to_zone(s, find(s, "Blood Operative"), "graveyard")
    master = to_hand(s, "Master of Death")
    life = s.state.players["p1"].life
    add_mana(s, "p1", U=1, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=master.id)  # its enters trigger: surveil 2
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} >= {"pay", "decline"}:
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and s.state.cards[operative.id].zone == "p1:graveyard"
    pick(s, "pay" if pay else "decline")
    play_out(s)
    assert (s.state.cards[operative.id].zone == "p1:hand") is pay
    assert s.state.players["p1"].life == life - (3 if pay else 0)
    roundtrip(s)


@pytest.mark.parametrize("pay", [True, False])
def test_gigapede_discards_a_card_to_return_from_the_graveyard(cards, pay):
    s = build(cards, p1=("Gigapede", "Llanowar Elves"))
    gigapede = to_zone(s, find(s, "Gigapede"), "graveyard")
    elves = to_zone(s, find(s, "Llanowar Elves"), "hand")
    d = to_upkeep_choice(s)
    assert d.player == "p1" and s.state.turn.number == 3
    pick(s, "pay" if pay else "decline")
    play_out(s, prefer=(elves.id,))
    assert (s.state.cards[gigapede.id].zone == "p1:hand") is pay  # "If you do, return this card to your hand"
    assert (s.state.cards[elves.id].zone == "p1:graveyard") is pay  # the discard is the cost
    roundtrip(s)


def test_ichorid_exiles_another_black_creature_card_never_itself(cards):
    s = build(cards, p1=("Ichorid", "Fanatic of the Harrowing"))
    ichorid = to_zone(s, find(s, "Ichorid"), "graveyard")
    # nothing else black in the graveyard: "a black creature card other than this card" can't be exiled, so no payment is offered
    for _ in range(60):
        d = s.state.rules.decision
        assert d is None or not {o.id for o in d.options} >= {"pay", "decline"}
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[ichorid.id].zone == "p1:graveyard"
    fodder = to_zone(s, find(s, "Fanatic of the Harrowing"), "graveyard")
    for _ in range(80):  # to the next upkeep of hers
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} >= {"pay", "decline"}:
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and s.state.turn.number == 5
    pick(s, "pay")
    play_out(s, prefer=(fodder.id,))
    assert s.state.cards[ichorid.id].zone == "p1:battlefield" and s.state.cards[fodder.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("already_there", [True, False])
def test_furious_forebear_sees_a_creature_die_only_after_it_is_in_the_graveyard(cards, already_there):
    """"Whenever a creature you control dies while this card is in your graveyard, you may pay {1}{W}. If you do, return this card
    from your graveyard to your hand." Not when it dies at the same moment as the creature (603.10a: it wasn't there before)."""
    s = build(cards, p1=("Rain of Daggers",), p2=("Furious Forebear",))
    forebear = to_zone(s, find(s, "Furious Forebear", "p2"), "graveyard" if already_there else "battlefield")
    token_creature(s, "p2", "Bear")
    rain = to_hand(s, "Rain of Daggers")
    add_mana(s, "p1", B=2, C=4)
    add_mana(s, "p2", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=rain.id, targets=["p2"])
    asked = None
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and {o.id for o in d.options} >= {"pay", "decline"}:
            asked = d
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    if already_there:
        assert asked is not None and asked.player == "p2"
        roundtrip(s)
        pick(s, "pay")
        play_out(s)
        assert s.state.cards[forebear.id].zone == "p2:hand"
    else:
        assert asked is None and s.state.cards[forebear.id].zone == "p2:graveyard"  # both died together: it never triggers
    roundtrip(s)
