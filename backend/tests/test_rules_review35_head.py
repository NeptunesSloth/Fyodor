"""Review 35 (head): falsifying the cards waves 37A, 37B, 38A, 38C, 38D and 39B made FULL (CR 2026-09-25). Real Oracle text
(tests/fixtures/review35_head_cards.json and the fixtures of those waves, from data/cards.sqlite); every scenario checks the replay and a save
and a load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import commander
from app.rules.characteristics import Characteristics
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, until
from tests.test_rules_wave37b_reanimation import activate, grave
from tests.test_rules_wave38c_cast_riders import play_out, plotted, zone
from tests.test_rules_wave38d_companion import companion_warnings
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

HERE = Path(__file__).parent / "fixtures"
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA: list = []
for i, (file, code) in enumerate([("review35_head_cards.json", "r35"), ("wave37a_durations_cards.json", "r35a"), ("wave37b_cards.json", "r35b"),
                                  ("wave38a_cards.json", "r35c"), ("wave38c_cards.json", "r35d"), ("wave39b_cards.json", "r35e")]):
    for j, c in enumerate(json.loads((HERE / file).read_text("utf-8"))):
        if c["name"] not in KNOWN:
            KNOWN.add(c["name"])
            EXTRA.append(card(c["name"], set_code=code, number=f"H{i}{j:03d}", **{k: v for k, v in c.items() if k != "name"}))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def to_main1(s, turn):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def attack(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, s.state.rules.decision.player, type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def block(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, s.state.rules.decision.player, type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


# -- Xu-Ifit: "Return target creature card from your graveyard to the battlefield. It's a Skeleton … and has no abilities." ----------
def test_xu_ifit_returned_creature_has_no_enters_abilities(cards):
    """Xu-Ifit ruling 2025-07-25: a "when it enters" ability is lost before it can trigger; one that makes it enter tapped doesn't apply."""
    s = build(cards, ["Xu-Ifit, Osteoharmonist", "Geralf's Messenger"], forests=12)
    xu = put(s, "Xu-Ifit, Osteoharmonist")
    msg = grave(s, "Geralf's Messenger")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    bob = life(s, "p2")
    activate(s, "p1", xu, targets=[msg.id])
    settle(s)
    back = s.state.cards[msg.id]
    assert back.zone == "p1:battlefield"
    assert life(s, "p2") == bob and s.state.rules.decision is None  # no "target opponent loses 2 life"
    assert not back.tapped
    check(s)


# -- Hercules: "Whenever Hercules is dealt damage for the first time each turn, put that many +1/+1 counters on him." ------------------
def test_hercules_blocked_by_two_counts_the_damage_of_both(cards):
    """603.2c, 120.3: two blockers deal their damage at once: one event, one trigger, "that many" is all of it."""
    s = build(cards, ["Hercules, Olympian Hero"], forests=20)
    herc = put(s, "Hercules, Olympian Hero")
    a, b = token(s, "p2", "A", "1/1"), token(s, "p2", "B", "1/1")
    to_main1(s, 3)
    attack(s, (herc, "p2"))
    block(s, (a, herc), (b, herc))
    s = reloaded(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "divide")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, amounts=[2, len(d.options) and int(d.resume["total"]) - 2])
    through_combat(s)
    h = s.state.cards[card_named(s, "Hercules, Olympian Hero").id]
    assert h.damage == 2
    assert h.counters.get("+1/+1", 0) == 1 + 2  # the attack's counter and the two damage
    check(s)


# -- Aven Interrupter: "exile target spell. It becomes plotted." + "Spells your opponents cast from graveyards or from exile cost {2} more" --
def test_aven_interrupter_plots_an_opponents_spell_for_its_owner_who_pays_the_tax(cards):
    """702.170d: the plotted card's OWNER may cast it on a later turn as a sorcery without paying its mana cost; 601.2f: the {2} more still applies."""
    s = build(cards, ["Aven Interrupter"], ["Divination"])
    aven = to_hand(s, "Aven Interrupter")
    div = to_hand(s, "Divination", "p2")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", U=1, C=2)
    act(s, "p2", type="cast_spell", card_id=div.id)
    mana(s, "p1", W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=aven.id)  # (Bob passed: Alice responds)
    play_out(s, prefer=(div.id,))
    assert zone(s, div) == "p2:exile" and plotted(s, div)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    with pytest.raises(ActionError):  # (Alice doesn't own it)
        act(s, "p1", type="cast_spell", card_id=div.id, free=True)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    hand = len(s.state.zones["p2:hand"])
    with pytest.raises(ActionError):  # (the {2} more: no mana)
        act(s, "p2", type="cast_spell", card_id=div.id, free=True)
    mana(s, "p2", C=2)
    act(s, "p2", type="cast_spell", card_id=div.id, free=True)
    play_out(s)
    assert len(s.state.zones["p2:hand"]) == hand + 2 and zone(s, div) == "p2:graveyard"
    check(s)


# -- Zirda: "Abilities you activate that aren't mana abilities cost {2} less to activate. This effect can't reduce the mana in that cost to less than one mana."
def test_zirda_reduces_an_x_cost_once_x_is_chosen(cards):
    """601.2f (602.2b): X is chosen first (601.2b), then the total cost is reduced: Geth's {X}{B} with X = 2 is {2}{B}, {2} less is {B}."""
    s = build(cards, ["Zirda, the Dawnwaker", "Geth, Lord of the Vault"], ["Grizzly Bears"], forests=12)
    put(s, "Zirda, the Dawnwaker")
    geth = put(s, "Geth, Lord of the Vault")
    bears = grave(s, "Grizzly Bears", "p2")
    mana(s, B=1)
    activate(s, "p1", geth, targets=[bears.id], x_value=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not any(s.state.players["p1"].mana.values())
    check(s)


# -- Zirda's companion condition: "Each permanent card in your starting deck has an activated ability." ---------------------------------------
def test_zirda_counts_activated_keywords_printed_without_reminder_text(cards):
    """702.6a equip, 702.122a crew: activated abilities. Bonesplitter's Oracle line is "Equip {1}" (no reminder text, so no colon); Smuggler's
    Copter's crew line has one. A line about such abilities is no such ability; Grizzly Bears has none."""
    zirda = "Zirda, the Dawnwaker"
    assert companion_warnings(cards, zirda, "Krenko, Mob Boss", [(1, "Bonesplitter"), (1, "Smuggler's Copter"), (5, "Forest")]) == []
    assert companion_warnings(cards, zirda, "Krenko, Mob Boss", [(1, "Bonesplitter"), (1, "Grizzly Bears")])
    assert not commander._activated(Characteristics(name="x", oracle_text="Equip abilities you activate cost {1} less to activate."))
    assert commander._activated(Characteristics(name="x", oracle_text="Equip legendary creature {3}"))
    assert commander._activated(Characteristics(name="x", oracle_text="Equip—Pay 3 life."))


# -- Sandman: "Return this card and target land card from your graveyard to the battlefield tapped." -----------------------------------------
def test_sandman_stays_when_its_only_target_is_gone(cards):
    """608.2b (the Slimefoot and Squee ruling 2023-04-14): with its target illegal the ability doesn't resolve: this card isn't returned either."""
    s = build(cards, ["Sandman, Shifting Scoundrel"], forests=12)
    sandman = grave(s, "Sandman, Shifting Scoundrel")
    forest = grave(s, "Forest")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, G=5)
    activate(s, "p1", sandman, targets=[forest.id])
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="set_prefs", hold_priority=False)
    settle(s)
    assert s.state.cards[sandman.id].zone == "p1:graveyard"
    check(s)
