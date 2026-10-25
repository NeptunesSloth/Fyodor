"""Wave 110G: single cards read from an exact wording (real Oracle text); each scenario checks replay and save/load.

* Portcullis: 610.3 exile until the artifact leaves; the count includes the entering creature.
* Acquisitions Expert: 700.8 party size sets how many cards the opponent reveals (701.20a).
* Serene Master: 701.12g exchanging two powers sets each to the other's previous value (613.4b), until end of combat.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build
from tests.wave110b_kit import attack, cast, check, mana, put, settle, to_hand

EXTRA = [
    real('Serene Master', '{1}{W}', 2, 'Creature — Human Monk',
         "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.", ('0', '2'), 'W'),
    real('Portcullis', '{4}', 4, 'Artifact',
         "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield under its owner's control when this artifact leaves the battlefield.", None, ''),
    real('Acquisitions Expert', '{1}{B}', 2, 'Creature — Human Rogue',
         'When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. You choose one of those cards. That player discards that card. (Your party consists of up to one each of Cleric, Rogue, Warrior, and Wizard.)', ('1', '2'), 'B'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_serene_master_exchanges_powers(cards):
    s = build(cards, ["Grizzly Bears"], ["Serene Master"])
    master = put(s, "Serene Master", "p2")
    bears = put(s, "Grizzly Bears")
    attack(s, bears)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": master.id, "attacker_id": bears.id}])
    for _ in range(10):
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # Master 0/2 blocks Bears 2/2: powers swap, so Bears (power 0) dies to 2 damage and Master lives
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[master.id].zone == "p2:battlefield"
    check(s)


def _portcullis(cards, others):
    s = build(cards, ["Portcullis", "Grizzly Bears", "Benalish Hero", "Llanowar Elves", "Test Shatter Charm"], [])
    port = put(s, "Portcullis")
    for name in ["Grizzly Bears", "Benalish Hero"][:others]:
        put(s, name)
    mana(s, "p1", G=1)
    return s, port


def _elves(s):
    return next(c for c in s.state.cards.values() if c.name == "Llanowar Elves")


@pytest.mark.parametrize("others,exiled", [(1, False), (2, True)])
def test_portcullis_exiles_the_third_creature(cards, others, exiled):
    """Two or more other creatures must already be on the battlefield."""
    s, port = _portcullis(cards, others)
    cast(s, "Llanowar Elves")
    settle(s)
    assert _elves(s).zone.endswith("exile") == exiled
    check(s)


def test_portcullis_leaving_returns_the_card(cards):
    s, port = _portcullis(cards, 2)
    cast(s, "Llanowar Elves")
    settle(s)
    assert _elves(s).zone.endswith("exile")
    mana(s, "p1", R=1)
    cast(s, "Test Shatter Charm", [port.id])
    assert _elves(s).zone == "p1:battlefield"
    check(s)


def test_acquisitions_expert_reveals_party_size_cards(cards):
    seen = []
    s = build(cards, ["Acquisitions Expert", "Soul Warden"], ["Grizzly Bears", "Llanowar Elves", "Goblin"])
    put(s, "Soul Warden")
    for name in ("Grizzly Bears", "Llanowar Elves", "Goblin"):
        to_hand(s, name, "p2")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Acquisitions Expert").id, targets=[])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.player, d.kind, len(d.options), d.min_choices))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert ("p2", "choose_cards", 3, 2) in seen and seen[-1] == ("p1", "choose_cards", 2, 1), seen  # Cleric + Rogue: reveals two
    assert len(s.state.zones["p2:hand"]) == 2
    check(s)
