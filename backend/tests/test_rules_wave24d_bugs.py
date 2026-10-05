"""Wave 24D: open bugs. Cancelling a cast at the target / mode choice (601.2 rewind), "You may X. Then Y.", mana-ability riders after
a sacrifice cost, "you may search" under a can't-search effect, manifest from the library under Grafdigger's Cage."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import build, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana, replay_matches, token
from tests.fixtures.cards import card, fixture_cards

EXTRA = [  # noqa: E501
    card("Finality", set_code="tst", number="24D-FI", mana_cost="{4}{B}{G}", cmc=6.0, type_line="Sorcery",
         oracle_text="You may put two +1/+1 counters on a creature you control. Then all creatures get -4/-4 until end of turn.",
         colors=["B", "G"], color_identity=["B", "G"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- (a) cancel ---------------------------------------------------------------------------------------------------------------
def test_cancel_target_choice_rewinds_cast(cards):
    """601.2c: the target choice can be cancelled; nothing was paid or moved (601.2 rewind)."""
    s = build(cards, "Lightning Bolt")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id)
    d = s.state.rules.decision
    assert d is not None and any(o.id == "cancel" for o in d.options)
    pick(s, "cancel")
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    assert s.state.cards[bolt.id].zone == "p1:hand" and not s.state.zones.get("stack")
    assert s.state.players["p1"].mana.get("R") == 1  # nothing paid
    act(s, "p1", type="cast_spell", card_id=bolt.id)  # and it can be cast again
    assert s.state.rules.decision is not None
    replay_matches(s)


# -- (b) "You may X. Then Y." -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer, power", [("yes", 3), ("no", 1)])
def test_may_first_sentence_only(cards, answer, power):
    """Declining "you may put two +1/+1 counters" doesn't skip "Then all creatures get -4/-4" (603.5, 608.2c; Finality)."""
    s = build(cards, "Finality")
    fin = to_hand(s, "Finality")
    big = token(s, "p1", "Big", "5/5")
    mana(s, B=1, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=fin.id)
    d = until_asked(s)
    while d is not None and d.kind != "confirm":
        pick(s, d.options[0].id)
        d = until_asked(s)
    assert d is not None
    pick(s, answer)
    settle(s)
    assert s.state.cards[big.id].zone == "p1:battlefield"
    assert ch(s, big).pt == (power, power)
    replay_matches(s)


# -- B-bucket #8: modal spells' recurring mode wordings ----------------------------------------------------------------------
EXTRA += [
    card("Doomfall", set_code="tst", number="24D-DF", mana_cost="{2}{B}", cmc=3.0, type_line="Sorcery",
         oracle_text="Choose one —\n• Target opponent exiles a creature they control.\n• Target opponent reveals their hand. You choose a nonland card from it. Exile that card.",
         colors=["B"], color_identity=["B"]),
]


def test_edict_exile_mode(cards):
    """Doomfall: "Target opponent exiles a creature they control." — the opponent chooses (private, 101.4), then it is exiled (not sacrificed)."""
    s = build(cards, "Doomfall")
    spell = to_hand(s, "Doomfall")
    a, b = token(s, "p2", "Alpha", "2/2"), token(s, "p2", "Beta", "3/3")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[0], targets=["p2"])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {a.id, b.id}
    pick(s, b.id)
    settle(s)
    assert s.state.cards[a.id].zone == "p2:battlefield"
    assert b.id not in s.state.cards or s.state.cards[b.id].zone != "p2:battlefield"  # (a token that left ceases to exist)
    replay_matches(s)


def test_cancel_mode_choice_rewinds_cast(cards):
    """601.2b: the mode choice can be cancelled too; the spell stays in hand, nothing paid."""
    s = build(cards, "Doomfall")
    spell = to_hand(s, "Doomfall")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = s.state.rules.decision
    assert d is not None and d.options[-1].id == "cancel"
    pick(s, "cancel")
    assert s.state.cards[spell.id].zone == "p1:hand" and s.state.rules.decision is None and not s.state.zones.get("stack")
    assert s.state.players["p1"].mana.get("B") == 1
