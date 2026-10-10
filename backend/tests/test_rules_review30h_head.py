"""Review 30 (head): wave 30 falsification (CR 2026-09-25). Real Oracle text (tests/fixtures/review30h_cards.json and the wave 29B fixtures, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

* 605.3a / 601.2g-h: a mana ability whose cost chooses objects (Ashnod's Altar) may be activated in the middle of a free cast's payment (a cascaded
  Lightning Bolt under Thalia costs {1}, 118.9d); the free cast isn't over while its payment prompt is set aside (``payment_outer``), so the
  wave 30A cleanup in engine.choose must not end it as "not cast".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, settle
from tests.test_rules_review29b_granted_faces import cascade_into, pass_until_stack_empty
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

HERE = Path(__file__).parent / "fixtures"
DATA = [*json.loads((HERE / "wave29b_cards.json").read_text("utf-8")), *json.loads((HERE / "review29b_cards.json").read_text("utf-8")),
        *json.loads((HERE / "review30h_cards.json").read_text("utf-8"))]
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r30h", number=f"H{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def choose(s, *options):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(options))


def test_a_free_cast_paid_with_an_altar_mid_payment_is_still_cast(cards):
    def setup(s):
        put(s, "Thalia, Guardian of Thraben", "p2")
        put(s, "Ashnod's Altar")
        act(s, "p1", type="set_prefs", payment="self")

    s, bolt, _ = cascade_into(cards, "Lightning Bolt", theirs=["Thalia, Guardian of Thraben"], mine=["Ashnod's Altar"], setup=setup)
    bear = creature(s, "p1", "Bear")
    creature(s, "p1", "Cub")
    choose(s, "yes")
    choose(s, "p2")  # (Bolt's target)
    assert s.state.rules.decision.resume["step"] == "pay_mana"
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    assert s.state.rules.payment_outer is not None
    choose(s, bear.id)  # (the creature sacrificed for {C}{C}: the pool now covers Thalia's {1})
    assert bolt.id not in s.state.zones["p1:library"], "the free cast was ended mid-payment"
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_a_foretold_card_is_cast_from_exile(cards):
    """702.143a: foretell exiles the card face down (the engine's owner-only "foretell" zone is exile); casting it later is casting a spell from
    exile, so Pia Nalaar, Consul of Revival ("Whenever you play a land from exile or cast a spell from exile, create a 1/1 … Thopter …") triggers."""
    from tests.test_rules_wave18a_hidden import to_own_turn

    s = build(cards, ["Demon Bolt", "Pia Nalaar, Consul of Revival"])
    put(s, "Pia Nalaar, Consul of Revival")
    bolt = to_hand(s, "Demon Bolt")
    bear = creature(s, "p2", "Bear")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bolt.id, ability=1)  # (the foretell special action, 702.143b)
    assert s.state.cards[bolt.id].zone == "p1:foretell"
    to_own_turn(s, 3)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and bear.id not in s.state.cards  # (it was cast and resolved)
    assert any(c.name == "Thopter" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


def test_an_evoked_spell_returned_to_hand_and_cast_again_is_not_sacrificed(cards):
    """702.74a: "When this permanent enters, if its evoke cost was paid, its controller sacrifices it." Solitude evoked (Swords to Plowshares
    pitched) is returned to its owner's hand by Unsubstantiate (a new object, 400.7); cast again for its mana cost, its evoke cost wasn't paid: it stays."""
    from tests.test_rules_wave30e_keywords import hints

    from tests.test_rules_review28d import respond_on

    s = build(cards, ["Solitude", "Swords to Plowshares"], ["Unsubstantiate"])
    respond_on(s)
    solitude, _ = to_hand(s, "Solitude"), to_hand(s, "Swords to Plowshares")
    remand = to_hand(s, "Unsubstantiate", "p2")
    (alt,) = hints(s.state, "p1", cards)["alt_castable"][solitude.id]
    act(s, "p1", type="cast_spell", card_id=solitude.id, alt_cost=alt["id"])
    mana(s, "p2", C=1, U=1)
    act(s, "p2", type="cast_spell", card_id=remand.id, targets=[solitude.id])
    settle(s)
    assert s.state.cards[solitude.id].zone == "p1:hand"
    mana(s, C=3, W=2)
    act(s, "p1", type="cast_spell", card_id=solitude.id)
    settle(s)
    assert s.state.cards[solitude.id].zone == "p1:battlefield"
    check(s)
