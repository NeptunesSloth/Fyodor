"""Wave 110D: Aura abilities that name the Aura, and named Aura tokens, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 607.1a, 602.2: Heliod's Punishment's granted "{T}: Remove a task counter from Heliod's Punishment. Then if it has no task counters on it, destroy Heliod's
  Punishment." counts the Aura's counters (608.2c "it" is the Aura) and destroys it at none; the creature can't attack or block and has only that ability.
* 701.21a, 608.2c: Hold for Ransom's "{7}: Hold for Ransom's controller sacrifices it and draws a card." — the Aura's controller sacrifices the creature only if
  they control it, and draws either way.
* 111.3, 303.4f: The Rani and Preston Garvey make a named Aura token attached to the permanent (not targeting it) with the stated enchant line and ability.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    full,
    mana,
    now,
    put,
    settle,
    to_hand,
    to_phase,
)


def ready(s, c):
    """Under its controller's control since the turn began (302.6)."""
    s.state.rules.controlled_since[c.id].turn = 0


CARDS = ["Heliod's Punishment", "Hold for Ransom", "The Rani", "Preston Garvey, Minuteman"]


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    assert full(name)


def test_heliods_punishment_counts_down_and_destroys_itself(cards):
    s = build(cards, ["Heliod's Punishment", "Templar Knight"])
    knight = put(s, "Templar Knight")
    aura = cast_on(s, "Heliod's Punishment", knight)
    ready(s, knight)
    assert now(s, aura).counters == {"task": 4} and [a.text[:3] for a in ch(s, knight).abilities] == ["{T}"]
    for left in (3, 2, 1):
        activate(s, knight, "{T}")
        assert now(s, aura).counters == {"task": left} and now(s, knight).tapped
        to_phase(s, "main1", turn=s.state.turn.number + 2)  # untaps in its controller's untap step
    activate(s, knight, "{T}")
    assert now(s, aura).zone == "p1:graveyard"  # no task counters left: destroyed
    check(s)


def test_hold_for_ransom_sacrifices_the_creature_and_draws(cards):
    s = build(cards, ["Hold for Ransom", "Templar Knight", "Dromosaur"])
    knight = put(s, "Templar Knight")
    cast_on(s, "Hold for Ransom", knight)
    ready(s, knight)
    before = len(s.state.zones["p1:hand"])
    mana(s, C=7)
    activate(s, knight, "{7}")
    assert now(s, knight).zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == before + 1
    check(s)


def test_hold_for_ransom_cannot_sacrifice_a_creature_its_controller_does_not_control(cards):
    s = build(cards, ["Hold for Ransom"], ["Templar Knight"])
    knight = put(s, "Templar Knight", "p2")
    aura = cast_on(s, "Hold for Ransom", knight)
    to_phase(s, "main1", turn=2)  # p2's turn: p2 controls the creature and activates it (sorcery speed)
    ready(s, knight)
    mana(s, "p2", C=7)
    before = len(s.state.zones["p1:hand"])
    activate(s, knight, "{7}", pid="p2")
    assert now(s, knight).zone == "p2:battlefield"  # p1 does not control it: 701.21a
    assert len(s.state.zones["p1:hand"]) == before + 1 and now(s, aura).zone == "p1:battlefield"  # p1, the Aura's controller, drew
    check(s)


def test_the_rani_makes_a_mark_that_goads_and_pumps(cards):
    s = build(cards, ["The Rani", "Templar Knight"], ["Dromosaur"])
    saur = put(s, "Dromosaur", "p2")
    rani = to_hand(s, "The Rani")
    mana(s, U=1, B=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=rani.id)
    settle(s, answers=())
    mark = next(c for c in s.state.cards.values() if c.name == "Mark of the Rani")
    assert mark.is_token and mark.attached_to == saur.id and ch(s, mark).colors == frozenset({"R"})
    assert ch(s, saur).pt == (4, 5)  # 2/3 + 2/2
    assert "goaded:p1" in ch(s, saur).imposed
    check(s)


def test_preston_garvey_settles_a_land(cards):
    s = build(cards, ["Preston Garvey, Minuteman", "Mountain"])
    put(s, "Preston Garvey, Minuteman")
    land = put(s, "Mountain")
    ready(s, land)
    to_phase(s, "begin_combat", turn=3)
    settle(s)
    settlement = next(c for c in s.state.cards.values() if c.name == "Settlement")
    assert settlement.attached_to == land.id and ch(s, settlement).subtypes >= {"Aura"}
    check(s)


def test_preston_garvey_attack_untaps_only_enchanted_permanents(cards):
    """Whenever Preston Garvey attacks, untap each enchanted permanent you control: the land with Settlement untaps, the plain land stays tapped."""
    s = build(cards, ["Preston Garvey, Minuteman", "Mountain", "Forest"])
    preston = put(s, "Preston Garvey, Minuteman")
    ready(s, preston)
    lands = [put(s, "Mountain"), put(s, "Forest")]
    to_phase(s, "begin_combat", turn=3)
    settle(s)
    enchanted = next(c for c in s.state.cards.values() if c.name == "Settlement").attached_to
    plain = next(c.id for c in lands if c.id != enchanted)
    act(s, "p1", type="tap", card_ids=[enchanted, plain])
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": preston.id, "target": "p2"}])
    settle(s)
    assert not s.state.cards[enchanted].tapped and s.state.cards[plain].tapped
    check(s)
