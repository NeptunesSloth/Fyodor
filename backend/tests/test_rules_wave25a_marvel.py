"""Wave 25A: the Marvel keywords mayhem and web-slinging (CR 702.187, 702.188). Real Oracle text, replay and save/load for each.

* 702.187b: "As long as you discarded this card this turn, you may cast it from your graveyard by paying [cost] rather than paying its
  mana cost" (an alternative cost; the card is that object only: 400.7); 702.187c: a bare "Mayhem" lets you play it from there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, token
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Raging Goblinoids', set_code='tst', number='M01', mana_cost='{4}{R}', cmc=5.0, type_line='Creature — Goblin Berserker Villain', oracle_text='Haste\nMayhem {2}{R} (You may cast this card from your graveyard for {2}{R} if you discarded it this turn. Timing rules still apply.)', power='5', toughness='4', colors=['R'], color_identity=['R'], keywords=['Mayhem', 'Haste'], layout='normal'),  # noqa: E501
    card('Oscorp Industries', set_code='tst', number='M02', cmc=0.0, type_line='Land', oracle_text='This land enters tapped.\nWhen this land enters from a graveyard, you lose 2 life.\n{T}: Add {U}, {B}, or {R}.\nMayhem (You may play this card from your graveyard if you discarded it this turn. Timing rules still apply.)', colors=[], color_identity=['B', 'R', 'U'], keywords=['Mayhem'], layout='normal'),  # noqa: E501
    card("Sandman's Quicksand", set_code='tst', number='M03', mana_cost='{1}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text="Mayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)\nAll creatures get -2/-2 until end of turn. If this spell's mayhem cost was paid, creatures your opponents control get -2/-2 until end of turn instead.", colors=['B'], color_identity=['B'], keywords=['Mayhem'], layout='normal'),  # noqa: E501
    card('Faithless Looting', set_code='tst', number='M04', mana_cost='{R}', cmc=1.0, type_line='Sorcery', oracle_text='Draw two cards, then discard two cards.\nFlashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)', colors=['R'], color_identity=['R'], keywords=['Flashback'], layout='normal'),  # noqa: E501
    card('Prison Break', set_code='tst', number='M05', mana_cost='{4}{B}', cmc=5.0, type_line='Sorcery', oracle_text='Return target creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.\nMayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)', colors=['B'], color_identity=['B'], keywords=['Mayhem'], layout='normal'),  # noqa: E501,
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Raging Goblinoids", "Oscorp Industries", "Sandman's Quicksand", "Prison Break"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def discard(s, name):
    """Discard ``name`` for real (Faithless Looting: draw two, then discard two — the first pick is the named card)."""
    put(s, "Faithless Looting", "hand")
    put(s, name, "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Faithless Looting").id)
    s.state.rules.priority == "p1" and act(s, "p1", type="pass_priority")
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        want = [o.id for o in d.options if o.card_id == find(s, name).id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=(want + [i for i in ids if i not in want])[: d.max_choices])
    answer(s)


def test_mayhem_casts_a_discarded_creature_from_the_graveyard_for_its_cost(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    discard(s, "Raging Goblinoids")
    gob = find(s, "Raging Goblinoids")
    assert gob.zone == "p1:graveyard"
    mana(s, R=1, C=2)  # mayhem {2}{R}, not its mana cost {4}{R}
    act(s, "p1", type="cast_spell", card_id=gob.id)
    answer(s)
    assert find(s, "Raging Goblinoids").zone == "p1:battlefield"
    roundtrip(s)


def test_mayhem_needs_the_card_to_have_been_discarded_this_turn(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    gob = put(s, "Raging Goblinoids", "graveyard")  # put there, not discarded
    mana(s, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=gob.id)
    roundtrip(s)


def test_mayhem_is_for_the_object_that_was_discarded(cards):
    s = build(cards, p1=("Raging Goblinoids", "Faithless Looting"))
    discard(s, "Raging Goblinoids")
    put(s, "Raging Goblinoids", "exile")  # a new object (400.7) when it comes back
    gob = put(s, "Raging Goblinoids", "graveyard")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=gob.id)


def test_a_mayhem_cost_paid_changes_the_spell_instead(cards):
    s = build(cards, p1=("Sandman's Quicksand", "Faithless Looting"))
    mine, theirs = token(s, "p1", "Mine", "3/3"), token(s, "p2", "Theirs", "3/3")
    discard(s, "Sandman's Quicksand")
    mana(s, B=1, C=3)  # mayhem {3}{B}
    act(s, "p1", type="cast_spell", card_id=find(s, "Sandman's Quicksand").id)
    answer(s)
    from tests.test_rules_attachments import ch

    assert ch(s, mine).pt == (3, 3) and ch(s, theirs).pt == (1, 1)  # only the opponents' creatures got -2/-2
    assert find(s, "Sandman's Quicksand").zone == "p1:graveyard"  # (not exiled: it isn't flashback)
    roundtrip(s)


def test_the_normal_cast_of_the_same_spell_hits_every_creature(cards):
    s = build(cards, p1=("Sandman's Quicksand",))
    mine, theirs = token(s, "p1", "Mine", "3/3"), token(s, "p2", "Theirs", "3/3")
    put(s, "Sandman's Quicksand", "hand")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Sandman's Quicksand").id)
    answer(s)
    from tests.test_rules_attachments import ch

    assert ch(s, mine).pt == (1, 1) and ch(s, theirs).pt == (1, 1)
    roundtrip(s)


def test_a_bare_mayhem_lets_you_play_the_land_from_the_graveyard(cards):
    s = build(cards, p1=("Oscorp Industries", "Faithless Looting"))
    discard(s, "Oscorp Industries")
    land = find(s, "Oscorp Industries")
    assert land.zone == "p1:graveyard"
    act(s, "p1", type="play_land", card_id=land.id)
    assert find(s, "Oscorp Industries").zone == "p1:battlefield"
    roundtrip(s)
