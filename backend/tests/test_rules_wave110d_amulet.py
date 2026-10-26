"""Wave 110D: Jeweled Amulet, real Oracle text. Every scenario checks the replay and a save and a load.

* 607.2e, 106.1: "Note the type of mana spent to pay this activation cost" is linked to the second ability: "Add one mana of this artifact's last noted type".
* 602.5b: the input ability is activated only with no charge counters on the Amulet.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana
from tests.wave110d_kit import ability, card_db as _kit_db, full, now, put_new, settle, to_phase  # noqa: F401

EXTRA = [real("Jeweled Amulet", "{1}", 1, "Artifact",
              "{1}, {T}: Put a charge counter on this artifact. Note the type of mana spent to pay this activation cost. Activate only if there are no charge counters on this artifact.\n"
              "{T}, Remove a charge counter from this artifact: Add one mana of this artifact's last noted type.")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Jeweled Amulet")).level == "FULL"


@pytest.mark.parametrize("color", ["R", "G", "C"])
def test_notes_the_type_and_adds_it_later(cards, color):
    s = build(cards, ["Jeweled Amulet"])
    am = put_new(s, "Jeweled Amulet")
    to_phase(s, "main1", turn=3)  # (untapped, no longer summoning sick)
    mana(s, "p1", **{color: 1})
    act(s, "p1", type="activate_ability", card_id=am.id, ability=ability(s, am, "{1}, {T}"), sources=[])
    settle(s)
    assert now(s, am).counters.get("charge") == 1
    with pytest.raises(ActionError):  # (a charge counter on it: no second note)
        act(s, "p1", type="activate_ability", card_id=am.id, ability=ability(s, am, "{1}, {T}"), sources=[])
    to_phase(s, "main1", turn=5)
    assert s.state.players["p1"].mana == {} and not s.state.players["p1"].mana_units
    act(s, "p1", type="activate_ability", card_id=am.id, ability=ability(s, am, "{T}, Remove"), sources=[])
    settle(s)
    p = s.state.players["p1"]
    got = dict(p.mana)
    for u in p.mana_units:
        got[u.sym] = got.get(u.sym, 0) + 1
    assert got == {color: 1} and now(s, am).counters.get("charge", 0) == 0
    check(s)
