"""Wave 8A: keyword pieces - modular N (702.43a) and "Partner with [name]" (702.124j's enters trigger).

* Modular N: the permanent enters with N +1/+1 counters; when it is put into a graveyard from the battlefield its
  controller may put a +1/+1 counter on target artifact creature for each +1/+1 counter it had (last known
  information, 113.6 / 608.2h).
* Partner with: when the permanent enters, target player may search their library for the named card, reveal it, put
  it into their hand, then shuffle (the pairing itself is app/rules/commander.py).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, cast, on_field, settle, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Arcbound Worker', set_code="tst", number="W00", mana_cost='{1}', cmc=1.0, type_line='Artifact Creature — Construct', oracle_text='Modular 1 (This creature enters with a +1/+1 counter on it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', colors=[], color_identity=[], keywords=['Modular']),  # noqa: E501
    card('Arcbound Stinger', set_code="tst", number="W01", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Insect', oracle_text='Flying\nModular 1 (This creature enters with a +1/+1 counter on it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', colors=[], color_identity=[], keywords=['Flying', 'Modular']),  # noqa: E501
    card('Arcbound Ravager', set_code="tst", number="W02", mana_cost='{2}', cmc=2.0, type_line='Artifact Creature — Beast', oracle_text='Sacrifice an artifact: Put a +1/+1 counter on this creature.\nModular 1 (This creature enters with a +1/+1 counter on it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', colors=[], color_identity=[], keywords=['Modular']),  # noqa: E501
    card('Arcbound Lancer', set_code="tst", number="W03", mana_cost='{7}', cmc=7.0, type_line='Artifact Creature — Beast', oracle_text='First strike\nModular 4 (This creature enters with four +1/+1 counters on it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', colors=[], color_identity=[], keywords=['First strike', 'Modular']),  # noqa: E501
    card('Arcbound Wanderer', set_code="tst", number="W04", mana_cost='{6}', cmc=6.0, type_line='Artifact Creature — Golem', oracle_text='Modular—Sunburst (This creature enters with a +1/+1 counter on it for each color of mana spent to cast it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', colors=[], color_identity=[], keywords=['Modular', 'Sunburst']),  # noqa: E501
    card('Pippin, Warden of Isengard', set_code="tst", number="W05", mana_cost='{B}{G}', cmc=2.0, type_line='Legendary Creature — Halfling Advisor', oracle_text='Partner with Merry, Warden of Isengard (When this creature enters, target player may put Merry into their hand from their library, then shuffle.)\n{1}, {T}: Create a Food token.\n{T}, Sacrifice four Foods: Other creatures you control get +3/+3 and gain haste until end of turn. Activate only as a sorcery.', power='2', toughness='2', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Partner with', 'Food', 'Partner']),  # noqa: E501
    card('Merry, Warden of Isengard', set_code="tst", number="W06", mana_cost='{1}{G}{W}', cmc=3.0, type_line='Legendary Creature — Halfling Advisor', oracle_text='Partner with Pippin, Warden of Isengard (When this creature enters, target player may put Pippin into their hand from their library, then shuffle.)\nWhenever one or more artifacts you control enter, create a 1/1 white Soldier creature token with lifelink. This ability triggers only once each turn.', power='1', toughness='4', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Partner with', 'Partner']),  # noqa: E501
    card('Kamber, the Plunderer', set_code="tst", number="W07", mana_cost='{3}{B}', cmc=4.0, type_line='Legendary Creature — Vampire Rogue', oracle_text='Partner with Laurine, the Diversion (When this creature enters, target player may put Laurine into their hand from their library, then shuffle.)\nLifelink\nWhenever a creature an opponent controls dies, you gain 1 life and create a Blood token. (It\'s an artifact with "{1}, {T}, Discard a card, Sacrifice this token: Draw a card.")', power='3', toughness='4', colors=['B'], color_identity=['B'], keywords=['Lifelink', 'Partner with', 'Partner']),  # noqa: E501
    card('Laurine, the Diversion', set_code="tst", number="W08", mana_cost='{2}{R}', cmc=3.0, type_line='Legendary Creature — Human Rogue', oracle_text='Partner with Kamber, the Plunderer (When this creature enters, target player may put Kamber into their hand from their library, then shuffle.)\nFirst strike\n{2}, Sacrifice an artifact or creature: Goad target creature. (Until your next turn, that creature attacks each combat if able and attacks a player other than you if able.)', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Partner with', 'Goad', 'First strike', 'Partner']),  # noqa: E501
]
FULL = ["Arcbound Worker", "Arcbound Stinger", "Arcbound Ravager", "Arcbound Lancer", "Pippin, Warden of Isengard",
        "Merry, Warden of Isengard", "Kamber, the Plunderer", "Laurine, the Diversion"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_modular_with_a_keyword_count_stays_manual(cards):
    assert coverage.of_card_data(cards.resolve("Arcbound Wanderer")).level != "FULL"  # "Modular—Sunburst"


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def test_modular_enters_with_counters_and_moves_them_when_it_dies(cards):
    s = build(cards, "Arcbound Worker", "Arcbound Stinger", "Lightning Bolt")
    stinger = to_hand(s, "Arcbound Stinger")
    mana(s, C=2)
    cast(s, stinger)
    worker = to_hand(s, "Arcbound Worker")
    mana(s, C=1)
    cast(s, worker)
    worker = s.state.cards[worker.id]
    assert worker.zone == "p1:battlefield" and counters(s, worker) == 1 and counters(s, stinger) == 1  # modular 1 (702.43a)
    act(s, "p1", type="set_counter", card_id=worker.id, kind="+1/+1", value=3)  # it grew: 3 counters as it dies
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[worker.id])
    settle(s)
    assert s.state.cards[worker.id].zone == "p1:graveyard"
    assert counters(s, stinger) == 1 + 3  # one +1/+1 counter for each it had (the first option of the "may": yes)
    roundtrip(s)


def test_modular_four_enters_with_four(cards):
    s = build(cards, "Arcbound Lancer")
    lancer = to_hand(s, "Arcbound Lancer")
    mana(s, C=7)
    cast(s, lancer)
    assert counters(s, lancer) == 4
    roundtrip(s)


def test_partner_with_fetches_the_named_partner(cards):
    s = build(cards, "Pippin, Warden of Isengard", "Merry, Warden of Isengard")
    pippin = to_hand(s, "Pippin, Warden of Isengard")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=pippin.id)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards" or d.kind == "choose_one":
            if d.kind == "choose_cards":
                assert [o.card_id for o in d.options] and all(s.state.cards[o.card_id].name == "Merry, Warden of Isengard"
                                                              for o in d.options)  # only the named card is offered
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:  # the "may" confirmation: search
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [d.options[0].id])
    merry = next(c for c in s.state.cards.values() if c.name == "Merry, Warden of Isengard")
    assert merry.zone == "p1:hand"
    roundtrip(s)
