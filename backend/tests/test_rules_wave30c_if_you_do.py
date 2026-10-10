"""Wave 30C: "If you do" (CR 118.12, 2026-09-25) checks that the player chose to pay an optional cost or started to pay a mandatory
one, "regardless of what events actually occurred" (the Standstill and Dermoplasm + Gather Specimens examples). Real Oracle text
(tests/fixtures/wave30c_if_you_do_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.

* A token returned to its owner's hand is deleted at once (111.7), a commander goes to the command zone instead (903.9b): the player
  still started the return, so the clause is true (Mirkwood Nurturer, Niambi: tests/test_rules_conditionals.py).
* Counters put with a reduction (Vorinclex halves 1 to 0): the cost was started, so Thought Gorger discards its controller's hand (the
  Devoted Druid ruling of 2018-12-07). Solemnity ("can't", 614.17b) stays false: tests/test_rules_review24c.py.
* A reflexive "When you do" (603.12) after counters reads the event: Wishing Well under Vorinclex puts no counter, so it casts nothing
  (the Auron ruling of 2025-06-06: the reflexive ability triggers "when you put a +1/+1 counter on it this way").
* A partial payment is no payment (118.3; the Egon ruling of 2021-02-05): "Sacrifice two creatures. If you do, …" is not read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_scripts import ch
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30c_if_you_do_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30c", number=f"I{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def answer(s, *prefer, limit=30):
    """Resolve everything; a choice is answered with ``prefer`` (when offered) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("token", [True, False])
def test_mirkwood_nurturer_counts_a_bounced_token(cards, token):
    """118.12: "return up to one other target permanent you control to its owner's hand. If you do, put a +1/+1 counter on this creature."
    A token is gone as it reaches the hand (ops.move_card), but the return was started, so the counter is put."""
    s = build(cards, ["Mirkwood Nurturer", "Grizzly Bears"])
    target = token_of(s, "p1", "Bear Token", "Token Creature — Bear", "2/2") if token else put(s, "Grizzly Bears")
    nurturer = to_hand(s, "Mirkwood Nurturer")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=nurturer.id)
    answer(s)
    # (the target is chosen as the ability goes on the stack: with a legal one, the one permanent comes back)
    assert (target.id not in s.state.cards) if token else s.state.cards[target.id].zone == "p1:hand"
    assert counters(s, nurturer) == 1
    check(s)


def test_thought_gorger_discards_when_the_counters_are_halved_to_none(cards):
    """118.12 / 118.11: Vorinclex halves the one counter to none, but the controller started putting counters: "If you do" is true."""
    s = build(cards, ["Thought Gorger", "Lightning Bolt"], ["Vorinclex, Monstrous Raider"])
    put(s, "Vorinclex, Monstrous Raider", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    gorger = to_hand(s, "Thought Gorger")
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=gorger.id)
    answer(s)
    assert counters(s, gorger) == 0 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_wishing_well_casts_nothing_when_the_counter_is_halved_to_none(cards):
    """603.12: the reflexive ability triggers on the event: no coin counter was put (Vorinclex), so nothing is cast."""
    s = build(cards, ["Wishing Well", "Lightning Bolt"], ["Vorinclex, Monstrous Raider"])
    put(s, "Vorinclex, Monstrous Raider", "p2")
    well = put(s, "Wishing Well")
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=well.id, ability=ability_index(s, well, "coin"))
    answer(s, "yes")
    assert counters(s, well, "coin") == 0 and s.state.cards[bolt.id].zone == "p1:graveyard" and life(s, "p2") == 40
    check(s)


@pytest.mark.parametrize(("text", "read"), [
    ("Sacrifice a creature. If you do, you gain 3 life.", True),
    ("Sacrifice two creatures. If you do, you gain 3 life.", False),
    ("Discard two cards. If you do, you gain 3 life.", False),
    ("Remove two +1/+1 counters from this creature. If you do, you gain 3 life.", False),
])
def test_a_partial_payment_is_no_payment_so_it_is_not_read(text, read):
    """118.3: a player can't pay a cost without the resources to pay it fully, and then does none of it (Egon's ruling): the engine
    would do part of it and then gain the life, so a mandatory count other than one is left to the players."""
    assert bool(scripts.definitions(ch("Host", "Creature", "When this creature enters, " + text[0].lower() + text[1:]))) is read
