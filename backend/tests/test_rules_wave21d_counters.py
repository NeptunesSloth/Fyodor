"""Wave 21D: the counters long tail (CR 2026-09-25).

* 603.6c / 111.7: "Whenever one or more cards are put into exile from your graveyard, put that many +1/+1 counters" (Rakshasa Vizier) and
  "… creature cards are put into your graveyard from anywhere, put that many …" (Voracious Brood): the number of cards of the batch.
* 122.6: "put a number of +1/+1 counters on it equal to your devotion to green" (Reverent Hunter): "put X … counters, where X is …".
* 614.1c: "enters with a +1/+1 counter on it for each other Zombie you control and each Zombie card in your graveyard" (Unbreathing Horde).
* 601.2i: "Whenever you cast a spell other than your first spell each turn" (Arcbound Tracker).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_hand
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_wave19c_ifyoudo import build, find, roundtrip, to_zone

EXTRA = [
    card('Rakshasa Vizier', set_code='tst', number='W21D1', mana_cost='{2}{B}{G}', cmc=4.0, type_line='Creature — Demon',
         oracle_text='Whenever one or more cards are put into exile from your graveyard, put that many +1/+1 counters on this creature.',
         power='4', toughness='4', colors=['B', 'G'], color_identity=['B', 'G'], keywords=[]),
    card('Voracious Brood', set_code='tst', number='W21D2', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Alien Insect',
         oracle_text='This creature enters with a +1/+1 counter on it for each creature card in your graveyard.\nWhenever one or more creature cards are put into your graveyard from anywhere, put that many +1/+1 counters on this creature.',
         power='0', toughness='0', colors=['G'], color_identity=['G'], keywords=[]),
    card('Reverent Hunter', set_code='tst', number='W21D3', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Human Archer',
         oracle_text='When this creature enters, put a number of +1/+1 counters on it equal to your devotion to green. (Each {G} in the mana costs of permanents you control counts toward your devotion to green.)',
         power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=[]),
    card('Unbreathing Horde', set_code='tst', number='W21D4', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Zombie',
         oracle_text='This creature enters with a +1/+1 counter on it for each other Zombie you control and each Zombie card in your graveyard.\nIf this creature would be dealt damage, prevent that damage and remove a +1/+1 counter from it.',
         power='0', toughness='0', colors=['B'], color_identity=['B'], keywords=[]),
    card('Arcbound Tracker', set_code='tst', number='W21D5', mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Dog',
         oracle_text='Menace\nModular 2 (This creature enters with two +1/+1 counters on it. When it dies, you may put its +1/+1 counters on target artifact creature.)\nWhenever you cast a spell other than your first spell each turn, put a +1/+1 counter on this creature.',
         power='0', toughness='0', colors=[], color_identity=[], keywords=['Menace', 'Modular']),
    card('Mind Rot', set_code='tst', number='W21D7', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery',
         oracle_text='Target player discards two cards.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Crypt Incursion', set_code='tst', number='W21D8', mana_cost='{2}{B}', cmc=3.0, type_line='Instant',
         oracle_text="Exile all creature cards from target player's graveyard. You gain 3 life for each card exiled this way.", power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Succumb to the Cold', set_code='tst', number='W21D6', mana_cost='{2}{U}', cmc=3.0, type_line='Instant',
         oracle_text='Tap one or two target creatures an opponent controls. Put a stun counter on each of them.',
         power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def counters(s, name):
    return find(s, name).counters.get("+1/+1", 0)


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def cast(s, name, **mana):
    c = to_hand(s, name)
    add_mana(s, "p1", **mana)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    return c


def test_vizier_counts_cards_put_into_exile_from_your_graveyard(cards):
    s = build(cards, p1=("Rakshasa Vizier", "Unbreathing Horde", "Voracious Brood", "Crypt Incursion"))
    to_zone(s, find(s, "Rakshasa Vizier"), "battlefield")
    to_zone(s, find(s, "Unbreathing Horde"), "graveyard")
    to_zone(s, find(s, "Voracious Brood"), "graveyard")
    c = to_hand(s, "Crypt Incursion")
    add_mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    settle(s)
    assert counters(s, "Rakshasa Vizier") == 2  # one trigger for the batch of two cards: "that many"
    roundtrip(s)


def test_discarded_creature_cards_grow_the_brood(cards):
    s = build(cards, p1=("Voracious Brood", "Rakshasa Vizier", "Unbreathing Horde", "Mind Rot"))
    to_zone(s, find(s, "Rakshasa Vizier"), "graveyard")  # (so it enters with a counter, and lives)
    brood = cast(s, "Voracious Brood", G=2, C=2)
    assert counters(s, "Voracious Brood") == 1
    for c in [c for c in s.state.cards.values() if c.owner == "p1" and c.zone == "p1:hand"]:
        to_zone(s, c, "library")  # (a hand of exactly what is discarded)
    to_hand(s, "Unbreathing Horde")
    c = to_hand(s, "Mind Rot")
    extra = [x for x in s.state.cards.values() if x.owner == "p1" and x.name == "Rakshasa Vizier"]
    act(s, "p1", type="move", card_ids=[extra[0].id], to={"zone": "hand"})
    add_mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    settle(s)
    assert s.state.cards[brood.id].counters.get("+1/+1", 0) == 3  # two creature cards discarded
    roundtrip(s)


def test_hunter_puts_devotion_many_counters(cards):
    s = build(cards, p1=("Voracious Brood", "Reverent Hunter", "Reverent Hunter"))
    first, second = [x for x in s.state.cards.values() if x.name == "Reverent Hunter" and x.owner == "p1"]
    to_zone(s, first, "graveyard")  # (so Brood enters with a counter, and lives)
    cast(s, "Voracious Brood", G=2, C=2)
    to_zone(s, second, "hand")
    add_mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=second.id)
    settle(s)
    assert s.state.cards[second.id].counters.get("+1/+1", 0) == 3  # {G}{G} (Brood) + {G} (Hunter itself)
    roundtrip(s)


def test_horde_enters_with_a_counter_for_each_other_zombie_and_zombie_card_in_the_graveyard(cards):
    s = build(cards, p1=("Unbreathing Horde", "Unbreathing Horde", "Unbreathing Horde"))
    a, b, c = [x for x in s.state.cards.values() if x.name == "Unbreathing Horde" and x.owner == "p1"]
    to_zone(s, a, "battlefield")
    to_zone(s, b, "graveyard")
    to_zone(s, c, "hand")
    add_mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.cards[c.id].counters.get("+1/+1", 0) == 2  # the Zombie on the battlefield and the one in the graveyard
    roundtrip(s)


def test_tracker_grows_on_the_second_spell_each_turn_only(cards):
    s = build(cards, p1=("Arcbound Tracker", "Lightning Bolt", "Lightning Bolt"))
    cast(s, "Arcbound Tracker", C=2)
    start = counters(s, "Arcbound Tracker")
    assert start == 2  # modular 2; casting it was the first spell of the turn
    for i, b in enumerate(c for c in list(s.state.cards.values()) if c.name == "Lightning Bolt" and c.owner == "p1"):
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
        add_mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
        settle(s)
        assert counters(s, "Arcbound Tracker") == start + i + 1  # each is a spell other than the first this turn
    roundtrip(s)
