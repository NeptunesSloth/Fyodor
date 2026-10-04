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
]
FULL = ['Dark Depths', 'Mazemind Tome', 'Kess, Dissident Mage', 'Scholar of the Lost Trove', 'Evie Frye', 'Teo, Spirited Glider', 'Celeborn the Wise', 'Fanatic of the Harrowing', "Talion's Messenger"]
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
