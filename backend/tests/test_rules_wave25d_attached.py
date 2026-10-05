"""Wave 25D: attached events (Auras, Equipment, Curses). Real Oracle text (tests/fixtures/wave25d_cards.json, from data/cards.sqlite);
each scenario replays and round-trips.

* 702.16n: "Enchanted creature has protection from black. This effect doesn't remove this Aura." (the Wards), "… doesn't remove Auras."
  (Spectra Ward), "protection from the chosen color" (the Aura's own "As ~ enters, choose a color")."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.game.state import GameState
from app.rules import attachments, coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, to_hand
from tests.test_rules_copy import choose, decision, on_battlefield, pay
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave25d_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t25d", number=f"B{i:02d}", **{k: v for k, v in c.items() if k not in ("name", "layout", "card_faces")})
         for i, c in enumerate(DATA)]
FODDER = [
    card("Probe Beast", set_code="t25d", number="B90", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Beast", oracle_text="", power="3",
         toughness="3", colors=["G"], color_identity=["G"]),
    card("Probe Curse", set_code="t25d", number="B91", mana_cost="{B}", cmc=1.0, type_line="Enchantment — Aura", oracle_text="Enchant creature",
         colors=["B"], color_identity=["B"]),
]


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def cast_on(s, name, target, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    pass_until_stack_empty(s)
    return c


def problem(s, source, host):
    return attachments.host_problem(Plan(s.state, "p1", s.cards, None), s.state.cards[source.id], host.id)


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [], "legalities": {"commander": "legal"}}).level == "FULL"


def test_a_ward_stays_but_another_black_aura_does_not(cards):
    s = build(cards, "Black Ward", "Probe Curse", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    ward = cast_on(s, "Black Ward", beast, W=1)
    assert s.state.cards[ward.id].attached_to == beast.id  # 702.16n: protection from black doesn't remove it
    assert "protection" in ch(s, beast).keywords
    assert problem(s, ward, beast) is None
    # a black Aura isn't what the Ward's text excuses (702.16n): it falls off
    other = on_battlefield(s, "Probe Curse")
    assert problem(s, other, beast) is not None
    roundtrip(s)


def test_spectra_ward_keeps_every_aura(cards):
    s = build(cards, "Spectra Ward", "Probe Curse", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    ward = cast_on(s, "Spectra Ward", beast, W=2, C=3)
    assert ch(s, beast).pt == (5, 5)
    other = on_battlefield(s, "Probe Curse")
    assert problem(s, ward, beast) is None and problem(s, other, beast) is None  # "doesn't remove Auras"
    roundtrip(s)


def test_the_chosen_color_is_the_auras_own_choice(cards):
    s = build(cards, "Flickering Ward", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    c = to_hand(s, "Flickering Ward")
    pay(s, W=1, C=1)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[beast.id])
    for _ in range(10):
        d = decision(s)
        if d is not None:
            choose(s, next(o.id for o in d.options if o.label == "White"))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[c.id].choices.get("Chosen color") == "White"
    assert s.state.cards[c.id].attached_to == beast.id  # it is white itself: the Aura is exempt (702.16n)
    from app.rules import protection

    prot = ch(s, beast)
    assert protection.protected_from(prot, ch(s, c)) and not protection.protected_from(prot, prot)  # white yes, the green Beast no
    roundtrip(s)


def settle(s, limit=30):
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    return c


def make(s, pid, name, kind, pt="2/2"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token Creature — {kind}", "power": p, "toughness": t, "text": ""})
    return next(c for c in s.state.cards.values() if c.name == name)


def test_a_crown_affects_every_creature_that_shares_a_type_with_the_enchanted_one(cards):
    s = build(cards, "Crown of Suspicion", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    cast_on(s, "Crown of Suspicion", beast, B=1, C=1)
    crown = next(c for c in s.state.cards.values() if c.name == "Crown of Suspicion")
    other_beast = make(s, "p2", "Their Beast", "Beast")  # any controller: "other creatures that share a creature type with it" (205.3m)
    elf = make(s, "p1", "Elf", "Elf Warrior")
    assert ch(s, beast).pt == (5, 2)
    index = next(a.index for a in ch(s, crown).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=index)
    settle(s)
    assert ch(s, beast).pt == (5, 2) and ch(s, other_beast).pt == (4, 1) and ch(s, elf).pt == (2, 2)  # the Aura is gone: 3/3 +2/-1, a 2/2 +2/-1
    roundtrip(s)


def test_a_crown_grants_protection_until_end_of_turn(cards):
    s = build(cards, "Crown of Awe", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    cast_on(s, "Crown of Awe", beast, W=1, C=1)
    crown = next(c for c in s.state.cards.values() if c.name == "Crown of Awe")
    other_beast = make(s, "p2", "Their Beast", "Beast")
    index = next(a.index for a in ch(s, crown).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=index)
    settle(s)
    from app.rules import protection

    assert protection.qualities(ch(s, other_beast)) and "protection" in ch(s, beast).keywords
    roundtrip(s)


def test_us_agent_attaches_the_equipment_token_it_made(cards):
    s = build(cards, "U.S.Agent, John Walker")
    agent = cast(s, "U.S.Agent, John Walker", W=1, C=3)
    shield = next(c for c in s.state.cards.values() if c.name == "Sturdy Shield")
    assert shield.attached_to == agent.id and "Equipment" in ch(s, shield).subtypes  # 701.3a: created, then attached
    assert ch(s, agent).pt == (4, 4)  # 3/2 +1/+2
    assert any(a.kind == "keywords" and "equip" in a.keywords for a in ch(s, shield).abilities)
    roundtrip(s)


def test_mabel_makes_a_legendary_equipment_that_can_equip(cards):
    s = build(cards, "Mabel, Heir to Cragflame")
    mabel = cast(s, "Mabel, Heir to Cragflame", R=1, W=1, C=1)
    cragflame = next(c for c in s.state.cards.values() if c.name == "Cragflame")
    c = ch(s, cragflame)
    assert "Legendary" in c.supertypes and "Equipment" in c.subtypes and cragflame.attached_to is None  # 301.5b: it enters unattached
    pay(s, C=2)
    index = next(a.index for a in c.abilities if a.kind == "keywords" and "equip" in a.keywords)
    act(s, "p1", type="activate_ability", card_id=cragflame.id, ability=index, targets=[mabel.id])
    settle(s)
    assert s.state.cards[cragflame.id].attached_to == mabel.id
    assert ch(s, mabel).pt == (4, 4) and {"vigilance", "trample", "haste"} <= ch(s, mabel).keywords
    roundtrip(s)
