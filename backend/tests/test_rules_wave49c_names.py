"""Wave 49C: a name chosen as the ability resolves, tested against a revealed card (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_names_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 201.4, 701.20a: "Choose a card name, then reveal a card at random from your hand. If that card has the chosen name, this artifact deals 2 damage to any target." (Cursed Scroll,
  Magus of the Scroll) - the name is typed first (public), then the table reveals one card of the hand; no card in hand means no card with the name was revealed.
* "Choose a card name, then reveal the top card of your library. If that card has the chosen name, sacrifice this artifact and draw three cards." (Diviner's Lockbox) - a wrong guess
  leaves the card on top.
* "All Slivers have '{T}: Choose a card name. Target opponent reveals a card at random from their hand. If that card has the chosen name, that player discards it.'" (Dementia Sliver).
* "Target player chooses a card name, then reveals the top card of their library. If that card has the chosen name, that player puts it into their hand. If it doesn't, the player puts it into
  their graveyard." (Petra Sphinx) - the target player names it; the card is revealed after. Vexing Arcanix ("Otherwise, they put it into their graveyard and this artifact deals 2 damage to
  them") stays manual: the damage belongs to the "otherwise" only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, ask, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave43b_kit import on_top

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_names_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"N{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Cursed Scroll", "Magus of the Scroll", "Diviner's Lockbox", "Dementia Sliver", "Petra Sphinx"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def run(s, *names, limit=30):
    """Resolve the stack; a card-name decision is answered with the next of ``names``, any other with its first option."""
    names = list(names)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.options and d.options[0].id == "__name__":
            act(s, d.player, type="choose", decision_id=d.id, name=names.pop(0))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def only_in_hand(s, name=None, pid="p1"):
    """Every other card of the hand goes to the graveyard, so the card revealed at random is this one (or none)."""
    keep = to_hand(s, name, pid) if name else None
    for cid in list(s.state.zones[f"{pid}:hand"]):
        if keep is None or cid != keep.id:
            act(s, pid, type="move", card_ids=[cid], to={"zone": "graveyard"})
    return keep


def test_the_cards_are_full(cards):
    # (Vexing Arcanix is FULL too: its player-named library choice is played in test_rules_resolved_library_choices.py)
    for name in [*FULL, "Vexing Arcanix"]:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize(("named", "damage"), [("Grizzly Bears", 2), ("Lightning Bolt", 0)])
def test_cursed_scroll_deals_damage_only_when_the_revealed_card_has_the_chosen_name(cards, named, damage):
    s = build(cards, ["Cursed Scroll", "Grizzly Bears"])
    scroll = put(s, "Cursed Scroll")
    only_in_hand(s, "Grizzly Bears")
    mana(s, C=3)
    activate(s, "p1", scroll, targets=["p2"])
    run(s, named)
    assert life(s, "p2") == 40 - damage
    check(s)


def test_cursed_scroll_with_an_empty_hand_still_names_a_card_and_does_nothing(cards):
    s = build(cards, ["Cursed Scroll"])
    scroll = put(s, "Cursed Scroll")
    only_in_hand(s)
    mana(s, C=3)
    activate(s, "p1", scroll, targets=["p2"])
    run(s, "Grizzly Bears")  # a name is chosen before anything is revealed (the ruling)
    assert life(s, "p2") == 40
    check(s)


@pytest.mark.parametrize(("named", "gone"), [("Grizzly Bears", True), ("Lightning Bolt", False)])
def test_diviners_lockbox_sacrifices_and_draws_three_only_on_the_right_name(cards, named, gone):
    s = build(cards, ["Diviner's Lockbox", "Grizzly Bears"])
    box = put(s, "Diviner's Lockbox")
    on_top(s, "Grizzly Bears")
    hand = len(s.state.zones["p1:hand"])
    mana(s, C=1)
    activate(s, "p1", box)
    run(s, named)
    assert (s.state.cards[box.id].zone == "p1:graveyard") is gone
    assert len(s.state.zones["p1:hand"]) == hand + (3 if gone else 0)
    assert (card_named(s, "Grizzly Bears").zone == "p1:hand") is gone  # (the top card is one of the three drawn)
    check(s)


def test_dementia_sliver_makes_the_opponent_discard_the_named_card(cards):
    s = build(cards, ["Dementia Sliver"], ["Grizzly Bears"])
    sliver = put(s, "Dementia Sliver")
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)
    only_in_hand(s, "Grizzly Bears", "p2")
    activate(s, "p1", sliver, "Choose a card name", targets=["p2"])
    run(s, "Grizzly Bears")
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:graveyard"
    check(s)


def test_dementia_sliver_leaves_a_card_with_another_name(cards):
    s = build(cards, ["Dementia Sliver"], ["Grizzly Bears"])
    sliver = put(s, "Dementia Sliver")
    to_phase(s, "main1", turn=3)
    only_in_hand(s, "Grizzly Bears", "p2")
    activate(s, "p1", sliver, "Choose a card name", targets=["p2"])
    run(s, "Lightning Bolt")
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:hand"
    check(s)


@pytest.mark.parametrize(("named", "zone"), [("Grizzly Bears", "p2:hand"), ("Lightning Bolt", "p2:graveyard")])
def test_petra_sphinx_has_the_target_player_name_a_card_and_reveal_the_top_card(cards, named, zone):
    s = build(cards, ["Petra Sphinx"], ["Grizzly Bears"])
    sphinx = put(s, "Petra Sphinx")
    top = on_top(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    top = on_top(s, "Grizzly Bears", "p2")  # (Bob drew his card for turn 2: the Bears go back on top)
    activate(s, "p1", sphinx, targets=["p2"])
    d = ask(s)
    assert d.player == "p2" and d.options[0].id == "__name__"  # Bob names the card, not Alice
    run(s, named)
    assert s.state.cards[top.id].zone == zone
    check(s)
