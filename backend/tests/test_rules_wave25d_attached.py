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
    card("Probe Spell Book", set_code="t25d", number="B92", mana_cost="{1}", cmc=1.0, type_line="Instant", oracle_text="", colors=[], color_identity=[]),
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


def to_decision(s, pid, limit=200):
    """Pass priority (answering nothing else) until ``pid`` has a decision."""
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision arrived")


def test_the_enchanted_creatures_controller_pays_to_untap_it(cards):
    """118.12: "that player may pay {4}. If the player does, untap the creature." The decision is the enchanted creature's controller's."""
    s = build(cards, "Paralyze")
    for _ in range(4):
        act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone != "p2:battlefield")],
            to={"player": "p2", "zone": "battlefield"})
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    cast_on(s, "Paralyze", ogre, B=1)
    assert s.state.cards[ogre.id].tapped  # "When this Aura enters, tap enchanted creature."
    act(s, "p1", type="pass_priority", until="next_turn")
    d = to_decision(s, "p2")
    assert d.player == "p2" and {o.id for o in d.options} >= {"pay", "decline"}  # Bob decides, not Alice
    choose(s, "pay")
    for _ in range(20):
        if not s.state.zones.get("stack") and decision(s) is None:
            break
        if decision(s) is not None:
            choose(s, decision(s).options[0].id)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert not s.state.cards[ogre.id].tapped  # untapped by the Aura's trigger (it hadn't untapped in the untap step)
    roundtrip(s)


def test_declining_leaves_the_creature_tapped(cards):
    s = build(cards, "Paralyze")
    for _ in range(4):
        act(s, "p2", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone != "p2:battlefield")],
            to={"player": "p2", "zone": "battlefield"})
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    cast_on(s, "Paralyze", ogre, B=1)
    act(s, "p1", type="pass_priority", until="next_turn")
    to_decision(s, "p2")
    choose(s, "decline")
    settle(s)
    assert s.state.cards[ogre.id].tapped
    roundtrip(s)


def test_a_static_counts_its_controllers_graveyard_not_the_auras(cards):
    """613.4c / 611.3a: "-X/-X, where X is the number of creature cards in its controller's graveyard": the enchanted creature's controller's."""
    from tests.test_rules_copy import game

    s = game(cards, alice=("Death's Approach", "Probe Beast"), bob=("Probe Beast",))
    mine = next(c for c in s.state.cards.values() if c.name == "Probe Beast" and c.owner == "p1")
    theirs = next(c for c in s.state.cards.values() if c.name == "Probe Beast" and c.owner == "p2")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    act(s, "p1", type="move", card_ids=[mine.id], to={"zone": "graveyard"})  # Alice's graveyard: one creature card
    cast_on(s, "Death's Approach", ogre, B=1)
    assert ch(s, ogre).pt == (3, 3)  # Bob's graveyard is empty: Alice's doesn't count
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
    assert ch(s, ogre).pt == (2, 2)
    roundtrip(s)


def test_lingering_death_makes_the_controller_sacrifice_the_creature_at_their_end_step(cards):
    s = build(cards, "Lingering Death")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    cast_on(s, "Lingering Death", ogre, B=1, C=1)
    assert ogre.id in s.state.zones["p2:battlefield"]
    act(s, "p1", type="pass_priority", until="next_turn")  # Alice's end step passes first: it's Bob's end step that counts
    for _ in range(80):
        if ogre.id not in s.state.zones.get("p2:battlefield", []) or s.state.turn.number >= 4:
            break
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id) if d.kind not in ("declare_attackers", "declare_blockers") else \
                act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blockers": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert ogre.id not in s.state.zones["p2:battlefield"]  # Bob sacrificed it (a token: it ceased to exist)
    roundtrip(s)


def test_roxannes_meteorite_token_deals_its_damage_as_it_enters(cards):
    """A quoted ability without its own period ("When this token enters, it deals 2 damage to any target") is read as the ability it is."""
    s = build(cards, "Roxanne, Starfall Savant", "Probe Beast")
    roxanne = to_hand(s, "Roxanne, Starfall Savant")
    pay(s, R=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=roxanne.id)
    for _ in range(12):  # the token's trigger asks for its target (115.1)
        d = decision(s)
        if d is not None:
            choose(s, "p2" if "p2" in {o.id for o in d.options} else d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    meteorite = next(c for c in s.state.cards.values() if c.name == "Meteorite")
    assert meteorite.tapped and s.state.players["p2"].life == 40 - 2  # "create a tapped … token", and it dealt 2 damage to the chosen player
    roundtrip(s)


def test_ward_sliver_gives_every_sliver_protection_from_the_chosen_color(cards):
    s = build(cards, "Ward Sliver")
    sliver = to_hand(s, "Ward Sliver")
    pay(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=sliver.id)
    for _ in range(10):
        d = decision(s)
        if d is not None:
            choose(s, next(o.id for o in d.options if o.label == "Red"))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    from app.rules import protection

    c = ch(s, s.state.cards[sliver.id])
    assert protection.qualities(c) and "protection" in c.keywords
    red = card("Probe Red", set_code="x", number="1", colors=["R"], color_identity=["R"])  # noqa: F841 (a red source, as characteristics)
    from dataclasses import replace

    assert protection.protected_from(c, replace(c, colors=frozenset({"R"}))) and not protection.protected_from(c, c)  # red yes, white no
    roundtrip(s)


def test_clues_become_equipment_that_can_equip(cards):
    """613.1d / 205.1b: "Clues you control are Equipment in addition to their other types and have "Equipped creature gets +2/+0" and equip {2}."
    (the type is added, 613.1f the abilities are granted, and the equip ability works like any Equipment's: 702.6)."""
    s = build(cards, "Armed with Proof", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    cast(s, "Armed with Proof", W=1, C=2)
    clues = [c for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield"]
    assert len(clues) == 2  # "investigate twice"
    c = ch(s, clues[0])
    assert {"Clue", "Equipment"} <= c.subtypes and "Artifact" in c.types
    index = next(a.index for a in c.abilities if a.kind == "keywords" and "equip" in a.keywords)
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=clues[0].id, ability=index, targets=[beast.id])
    settle(s)
    assert s.state.cards[clues[0].id].attached_to == beast.id and ch(s, beast).pt == (5, 3)  # +2/+0
    roundtrip(s)


def test_dan_lewis_only_noncreature_non_equipment_artifacts(cards):
    s = build(cards, "Dan Lewis", "U.S.Agent, John Walker")
    cast(s, "U.S.Agent, John Walker", W=1, C=3)
    shield = next(c for c in s.state.cards.values() if c.name == "Sturdy Shield")  # already an Equipment: not changed again
    act(s, "p1", type="create_token", player="p1", token={"name": "Trinket", "type_line": "Token Artifact — Treasure", "text": ""})
    trinket = next(c for c in s.state.cards.values() if c.name == "Trinket")
    on_battlefield(s, "Dan Lewis")
    equips = lambda c: sum(1 for a in ch(s, c).abilities if a.kind == "keywords" and "equip" in a.keywords)  # noqa: E731
    assert "Equipment" in ch(s, trinket).subtypes and equips(trinket) == 1
    assert equips(shield) == 1  # its own equip {2}, nothing granted on top
    roundtrip(s)


def test_remove_all_counters_takes_every_kind(cards):
    """122.8 / 701.? "remove all counters from it": each kind the creature has, as many as there are."""
    s = build(cards, "Enchanted River's Grasp")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    act(s, "p1", type="counter", card_ids=[ogre.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[ogre.id], kind="shield", delta=1)
    cast_on(s, "Enchanted River's Grasp", ogre, U=1, C=2)
    got = s.state.cards[ogre.id]
    assert got.tapped and not any(v for v in got.counters.values())  # tapped, every counter gone
    assert ch(s, ogre).pt == (3, 3)
    roundtrip(s)


def test_an_aura_returns_from_the_graveyard_attached_to_a_target(cards):
    """303.4i / 701.3: "Return this card from your graveyard to the battlefield attached to target creature." — the Aura enters attached (the host is a
    target of the ability, 115.1); a host it can't enchant leaves it in the graveyard."""
    s = build(cards, "Gryff's Boon", "Probe Beast")
    beast = on_battlefield(s, "Probe Beast")
    boon = next(c for c in s.state.cards.values() if c.name == "Gryff's Boon")
    act(s, "p1", type="move", card_ids=[boon.id], to={"zone": "graveyard"})
    pay(s, W=1, C=3)
    index = next(a.index for a in ch(s, boon).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=boon.id, ability=index, targets=[beast.id])
    settle(s)
    assert s.state.cards[boon.id].zone == "p1:battlefield" and s.state.cards[boon.id].attached_to == beast.id
    assert ch(s, beast).pt == (4, 3) and "flying" in ch(s, beast).keywords
    roundtrip(s)


def test_unfinished_business_attaches_the_auras_to_the_creature_it_returned(cards):
    s = build(cards, "Unfinished Business", "Probe Beast", "Probe Curse")
    beast = next(c for c in s.state.cards.values() if c.name == "Probe Beast")
    curse = next(c for c in s.state.cards.values() if c.name == "Probe Curse")
    for c in (beast, curse):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    spell = to_hand(s, "Unfinished Business")
    pay(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[beast.id, curse.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[beast.id].zone == "p1:battlefield"
    assert s.state.cards[curse.id].zone == "p1:battlefield" and s.state.cards[curse.id].attached_to == beast.id  # "attached to that creature"
    roundtrip(s)


def test_mantle_of_the_ancients_returns_auras_to_the_enchanted_creature(cards):
    s = build(cards, "Mantle of the Ancients", "Probe Beast", "Probe Curse")
    beast = on_battlefield(s, "Probe Beast")
    curse = next(c for c in s.state.cards.values() if c.name == "Probe Curse")
    act(s, "p1", type="move", card_ids=[curse.id], to={"zone": "graveyard"})
    spell = to_hand(s, "Mantle of the Ancients")
    pay(s, W=2, C=3)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[beast.id])
    for _ in range(20):
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[curse.id].zone == "p1:battlefield" and s.state.cards[curse.id].attached_to == beast.id
    roundtrip(s)


def test_a_spell_returns_itself_from_the_graveyard_when_a_forest_enters(cards):
    """113.6m: an instant's triggered ability that works from the graveyard is no part of what the spell does as it resolves."""
    s = build(cards, "Reach of Branches")
    spell = to_hand(s, "Reach of Branches")
    pay(s, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert s.state.cards[spell.id].zone == "p1:graveyard"
    assert any(c.name == "Treefolk Shaman" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    for _ in range(10):
        d = decision(s)
        if d is not None:
            choose(s, next((o.id for o in d.options if o.label == "Yes"), d.options[0].id))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[spell.id].zone == "p1:hand"
    roundtrip(s)


def test_genju_animates_its_forest_and_comes_back_when_it_dies(cards):
    """"{2}: Enchanted Forest becomes a 4/4 … It's still a land." and "When enchanted Forest is put into a graveyard, you may return this card from
    your graveyard to your hand." (the Aura is in the graveyard by the time the trigger resolves: 400.7f)."""
    s = build(cards, "Genju of the Cedars", "Doom Blade")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:4]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    genju = cast_on(s, "Genju of the Cedars", forests[0], G=1)
    assert s.state.cards[genju.id].attached_to == forests[0].id
    index = next(a.index for a in ch(s, genju).abilities if a.kind == "activated")
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=genju.id, ability=index)
    settle(s)
    c = ch(s, forests[0])
    assert c.is_creature and c.is_land and c.pt == (4, 4)  # "It's still a land"
    blade = to_hand(s, "Doom Blade")
    pay(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=blade.id, targets=[forests[0].id])
    for _ in range(20):
        d = decision(s)
        if d is not None:
            choose(s, next((o.id for o in d.options if o.label == "Yes"), d.options[0].id))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[forests[0].id].zone == "p1:graveyard" and s.state.cards[genju.id].zone == "p1:hand"
    roundtrip(s)


def test_a_curse_limits_the_enchanted_players_spells(cards):
    """601.3 / 611.3a: "Enchanted player can't cast more than one spell each turn." — the Aura's prohibition applies to the player it's attached to."""
    from app.game.errors import ActionError

    s = build(cards, "Curse of Exhaustion", "Probe Spell Book")
    curse = to_hand(s, "Curse of Exhaustion")
    pay(s, W=2, C=2)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=curse.id, targets=["p1"])  # (Alice curses herself: the one player this scenario acts for)
    pass_until_stack_empty(s)
    assert s.state.cards[curse.id].attached_player == "p1"
    book = to_hand(s, "Probe Spell Book")
    pay(s, C=2)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=book.id)  # the Curse was the first spell this turn
    roundtrip(s)


def test_grievous_wound_the_enchanted_player_cant_gain_life_and_loses_half_when_dealt_damage(cards):
    from app.rules import cant_gain

    s = build(cards, "Grievous Wound", "Lightning Bolt")
    wound = to_hand(s, "Grievous Wound")
    pay(s, B=2, C=3)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=wound.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.cards[wound.id].attached_player == "p2"
    plan = Plan(s.state, "p1", s.cards, None)
    assert cant_gain.why_not(plan, "p2") is not None and cant_gain.why_not(plan, "p1") is None  # only the enchanted player
    bolt = to_hand(s, "Lightning Bolt")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 40 - 3 - 19  # 37 life, then "lose half their life, rounded up" (19)
    roundtrip(s)


def test_brand_of_ill_omen_stops_the_enchanted_creatures_controller_casting_creatures(cards):
    from app.game.errors import ActionError

    s = build(cards, "Brand of Ill Omen", "Probe Beast", "Probe Spell Book", "U.S.Agent, John Walker")
    beast = on_battlefield(s, "Probe Beast")
    cast_on(s, "Brand of Ill Omen", beast, R=1, C=3)
    agent = to_hand(s, "U.S.Agent, John Walker")
    pay(s, W=1, C=3)
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=agent.id)  # a creature spell
    book = to_hand(s, "Probe Spell Book")
    act(s, "p1", type="cast_spell", card_id=book.id)  # a noncreature one is fine
    roundtrip(s)


def test_a_curse_asks_the_attacking_player_whether_to_make_a_zombie(cards):
    """118.12-style choice by another player: "that attacking player may create a tapped 2/2 black Zombie creature token." — Bob decides, Bob gets it."""
    from types import SimpleNamespace

    s = build(cards, "Curse of Shallow Graves")
    ogre = make(s, "p2", "Ogre", "Ogre", "3/3")
    cast_on(s, "Curse of Shallow Graves", SimpleNamespace(id="p1"), B=1, C=2)  # (Alice is the enchanted player)
    act(s, "p1", type="pass_priority", until="next_turn")
    d = None
    for _ in range(60):
        d = decision(s)
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            break
        if d is not None:
            choose(s, d.options[0].id) if d.options else act(s, d.player, type=d.kind, **{"attackers": []})
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p1"}])
    for _ in range(20):
        d = decision(s)
        if d is not None and {o.id for o in d.options} == {"pay", "decline"}:
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else choose(s, d.options[0].id)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2" and "Zombie" in d.prompt  # the attacking player decides
    choose(s, "pay")
    settle(s)
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p2:battlefield"]
    assert len(zombies) == 1 and zombies[0].tapped
    roundtrip(s)


def test_unifying_theory_the_caster_pays_and_draws(cards):
    s = build(cards, "Unifying Theory", "Probe Spell Book")
    on_battlefield(s, "Unifying Theory")
    for _ in range(2):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone != "p1:battlefield")],
            to={"player": "p1", "zone": "battlefield"})
    book = to_hand(s, "Probe Spell Book")
    pay(s, C=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=book.id)
    d = to_decision(s, "p1")
    assert d.player == "p1"
    choose(s, "pay")
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1  # the spell left the hand, one card drawn ("If the player does, they draw a card")
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
