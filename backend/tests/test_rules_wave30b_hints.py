"""Wave 30B: the castable hint agrees with the real cast (CR 601.2f, 119.4), real Oracle text (tests/fixtures/wave30b_hints_cards.json).

The hint already prices the spell with the cast's own ``spell_cost`` (Thalia's tax, commander tax, "cast from anywhere other than your hand"
reductions); the one thing it did not share was 119.4 *across* payments: ``_find_payment(reserve=plan.reserved_life)`` leaves a spell's
additional life cost out of the life that pays Phyrexian mana, ``can_pay`` didn't. K'rrik ("For each {B} in a cost, you may pay 2 life") and
Fumarole ("As an additional cost to cast this spell, pay 3 life.", {3}{B}{R}) with {B} unpaid: 3 + 2 life needed, so 4 life is refused."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30b_hints_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30b", number=f"H{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def agree(s, cards, cid, expect, **kw):
    """The hint says ``expect``, and the cast then does the same (a refused cast leaves the table as it was)."""
    assert (cid in hints(s.state, "p1", cards)["castable"]) is expect
    if expect:
        act(s, "p1", type="cast_spell", card_id=cid, **kw)
        assert s.state.cards[cid].zone.endswith(("stack", "graveyard", "battlefield"))
    else:
        zone = s.state.cards[cid].zone
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=cid, **kw)
        assert s.state.cards[cid].zone == zone
    check(s)


@pytest.mark.parametrize(("hp", "ok"), [(2, False), (4, False), (5, True)])
def test_additional_life_and_life_for_mana_are_one_119_4_budget(cards, hp, ok):
    # Fumarole's 3 life is paid first; K'rrik's 2 life then pays the {B} the pool lacks (119.4: each payment needs the life it takes)
    s = build(cards, ["Fumarole", "K'rrik, Son of Yawgmoth"], ["Grizzly Bears"], islands=3)
    put(s, "K'rrik, Son of Yawgmoth")
    bear, island = put(s, "Grizzly Bears", "p2"), put(s, "Island", "p2")
    fumarole = to_hand(s, "Fumarole")
    act(s, "p1", type="set_life", player="p1", value=hp)
    mana(s, C=4, R=1)
    agree(s, cards, fumarole.id, ok, targets=[bear.id, island.id], target_counts=[1, 1])
    assert life(s) == (hp - 5 if ok else hp)


def test_thalia_taxes_the_hint_and_the_cast_alike(cards):
    s = build(cards, ["Opt"], ["Thalia, Guardian of Thraben"])
    put(s, "Thalia, Guardian of Thraben", "p2")  # (everyone's noncreature spells: 601.2f)
    opt = to_hand(s, "Opt")
    mana(s, U=1)
    agree(s, cards, opt.id, False)
    mana(s, C=1)
    agree(s, cards, opt.id, True)


def test_commander_tax_and_a_reduction_for_not_casting_from_hand_are_in_the_hint(cards):
    # Krenko {2}{R}{R} from the command zone with 2 tax: {4}{R}{R}; Savvy Trader's "Spells you cast from anywhere other than your hand cost {1} less"
    s = build(cards, ["Savvy Trader"])
    krenko = card_named(s, "Krenko, Mob Boss")
    act(s, "p1", type="commander_tax", commander=krenko.commander_key, value=2)
    mana(s, R=2, C=3)
    agree(s, cards, krenko.id, False)  # {4}{R}{R}: one short
    put(s, "Savvy Trader")
    agree(s, cards, krenko.id, True)  # {3}{R}{R}
    assert s.state.players["p1"].mana == {}
