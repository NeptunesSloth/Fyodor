"""Break-it playtest B4 (correctness of the fast end step): Kiki-Jiki, Mirror Breaker and Pestermite repeated into a board of hasty copies,
each with its own "Sacrifice it at the beginning of the next end step" (a delayed trigger per copy, 603.7). The end step's sacrifices
are read faster on a big board (replacements._exile_static_sources and the read passes of the step scans); what they do is unchanged:

* the identical sacrifice triggers go on the stack without an order question (the grouped "Auto order");
* each copy dies on its own, and Blood Artist's trigger for it resolves before the next sacrifice (603.3: it is put on the stack above
  the rest, and each player gets priority between, 117.3b);
* with Rest in Peace on the table every copy is exiled instead (614.1a) and nothing dies;
* the replay and a save and a load give the same table.

The board is made by activating Kiki-Jiki again and again (each copy's Pestermite trigger untaps it), not by REPEAT. Real Oracle text
(Scryfall)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, life, put

KIKI, PEST, ARTIST, RIP = "Kiki-Jiki, Mirror Breaker", "Pestermite", "Blood Artist", "Rest in Peace"
EXTRA = [
    real(KIKI, "{2}{R}{R}{R}", 5, "Legendary Creature — Goblin Shaman", "Haste\n{T}: Create a token that's a copy of target nonlegendary creature you "
         "control, except it has haste. Sacrifice it at the beginning of the next end step.", ("2", "2"), "R"),
    real(PEST, "{2}{U}", 3, "Creature — Faerie Rogue", "Flash\nFlying\nWhen this creature enters, you may tap or untap target permanent.", ("2", "1"), "U"),
    real(ARTIST, "{1}{B}", 2, "Creature — Vampire",
         "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.", ("0", "1"), "B"),
    real(RIP, "{1}{W}", 2, "Enchantment",
         "When Rest in Peace enters, exile all graveyards.\nIf a card or token would be put into a graveyard from anywhere, exile it instead.", None, "W"),
]
COPIES = 24


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _copies(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]


def _board(cards, *extra):
    s = build(cards, [KIKI, PEST, *extra])
    kiki, pest = put(s, KIKI), put(s, PEST)
    for name in extra:
        put(s, name)
    to_phase(s, "main1", turn=3)
    for _ in range(COPIES):
        act(s, "p1", type="activate_ability", card_id=kiki.id, ability=1, targets=[pest.id])
        for _ in range(20):  # the copy's Pestermite trigger: target Kiki-Jiki, untap it
            d = s.state.rules.decision
            if d is None:
                if not s.state.zones.get("stack"):
                    break
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[kiki.id if kiki.id in ids else "untap" if "untap" in ids else ids[0]])
    assert len(_copies(s)) == COPIES and not s.state.zones.get("stack")
    return s


def _through_the_end_step(s):
    """From "No attack" to the next turn. Each Blood Artist target asked: Bob; returns how many copies were left at each such question."""
    left_at_target, kinds = [], []
    for _ in range(400):
        if s.state.turn.number > 3:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[])  # "No attack"
        elif d is not None:
            kinds.append(d.kind)
            ids = [o.id for o in d.options]
            if "p2" in ids:
                left_at_target.append(len(_copies(s)))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority", until="next_turn")
    assert s.state.turn.number > 3
    return left_at_target, kinds


def test_each_copy_dies_on_its_own_and_blood_artist_drains_between_the_sacrifices(cards):
    s = _board(cards, ARTIST)
    copies = _copies(s)
    alice, bob = life(s), life(s, "p2")
    left_at_target, kinds = _through_the_end_step(s)
    assert "order" not in kinds  # identical sacrifice triggers: the grouped auto order, no question
    assert not any(s.state.cards.get(c.id) is not None and s.state.cards[c.id].zone == "p1:battlefield" for c in copies)
    assert life(s, "p2") == bob - COPIES and life(s) == alice + COPIES
    # one Blood Artist trigger per copy, each put on the stack (and targeted) as its copy died, before the next sacrifice resolved
    assert left_at_target == list(range(COPIES - 1, -1, -1))
    check(s)


def test_with_rest_in_peace_each_copy_is_exiled_instead_and_nothing_dies(cards):
    s = _board(cards, ARTIST, RIP)
    copies = _copies(s)
    alice, bob = life(s), life(s, "p2")
    left_at_target, kinds = _through_the_end_step(s)
    assert "order" not in kinds and left_at_target == []  # exiled, not dead: Blood Artist never triggers (700.4)
    assert not any(s.state.cards.get(c.id) is not None and s.state.cards[c.id].zone == "p1:battlefield" for c in copies)
    assert (life(s), life(s, "p2")) == (alice, bob)
    assert not any(c.is_token for c in s.state.cards.values() if c.zone.endswith(":graveyard"))
    check(s)
