"""Review 41 probes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review41_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r41", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_probe_groups(cards):
    s = build(cards, ["Dense Foliage", "Arc Lightning", "Grizzly Bears"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Arc Lightning").id, targets=[bears.id, "p2"], target_counts=[2], division=[2, 1])
    print(s.state.rules.decision)


def test_probe_twincast(cards):
    s = build(cards, ["Dense Foliage", "Twincast", "Lightning Bolt", "Grizzly Bears"])
    put(s, "Dense Foliage")
    bears = put(s, "Grizzly Bears")
    mana(s, R=1, U=2)
    stops(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    print(s.state.zones.get("stack"), s.state.rules.decision)
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Twincast").id, targets=[bolt.id])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            print(d.kind, d.prompt, [(o.id, o.label) for o in d.options])
            assert bears.id not in [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    check(s)


TALION = "Talion, the Kindly Lord"


@pytest.mark.parametrize(("number", "drains"), [(4, True), (1, False)])
def test_probe_talion_x(cards, number, drains):
    s = build(cards, [TALION], ["Blaze"])
    stops(s)
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, TALION).id)
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[str(number)])
    settle(s)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=1, C=3)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Blaze", "p2").id, targets=["p1"], x_value=3)  # {X}{R} with X 3: mana value 4 (202.3e)
    settle(s)
    assert (s.state.players["p2"].life == 38) == drains
    check(s)


def test_probe_druid_class(cards):
    from tests.test_rules_wave34b_activated import activate
    from tests.wave9c_kit import pt
    from app.rules.plan import Plan

    s = build(cards, ["Druid Class"])
    druid = put(s, "Druid Class")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]
    for f in forests[:3]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    settle(s)
    mana(s, G=2, C=5)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=1)
    settle(s)
    act(s, "p1", type="activate_ability", card_id=druid.id, ability=3)
    settle(s)
    d = s.state.rules.decision
    print("decision", d and (d.kind, d.prompt, [o.label for o in d.options]))
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[forests[0].id])
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[forests[0].id])
    print(ch.types, ch.keywords, ch.pt, pt(s, "Forest"))
    act(s, "p1", type="move", card_ids=[forests[3].id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forests[3].id)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[forests[0].id])
    from app.rules import sba
    print(ch.types, ch.keywords, sba.power(s.state.cards[forests[0].id], ch), sba.toughness(s.state.cards[forests[0].id], ch), [a.text for a in ch.abilities])
    print(s.state.players["p1"].life)
    check(s)
