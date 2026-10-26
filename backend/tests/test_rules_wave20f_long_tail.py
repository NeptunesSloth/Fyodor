"""Wave 20F: the small long-tail families (token copies, transform, sagas, looking at another library, kicked casts),
researched against CR 2026-09-25.

* 111.12, 608.2h: "When this creature dies, create a token that's a copy of it" — the copy of the object as it last existed.
* 508.4: a token copy "tapped and attacking" (Flamerush Rider) is attacking but never "attacked"; "Exile it at end of combat".
* 707.9b: "except it's a 2/2 black Zombie in addition to its other colors and types"; "its name is …" (the printed name).
* 701.27a: "transform it" (the source in its own trigger) and "remove those counters and transform it".
* 714: a Saga chapter's leading "If …" is a plain conditional instruction, not an intervening "if" (603.4).
* 702.33d: "When you cast this spell, if it was kicked, …" reads the spell's own payment record.
* 401, 404.1: "look at the top card of target player's library. You may put that card into their graveyard" (its owner's).

Every scenario uses the cards' current Oracle text (tests/fixtures/wave20f_cards.json, from data/cards.sqlite), checks that
replaying the recorded history reproduces the table, and that a save/load round trip keeps it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import (
    cast,
    ch,
    drive,
    find,
    game,
    mana,
    put,
    responsive,
    roundtrip,
    tokens,
)

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave20f_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t20f", number=f"F{i:02d}", **({"image_uris": None} if c.get("card_faces") else {}),
              **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def level(name):
    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [n for n in NAMES])
def test_the_promoted_cards_are_full(name):
    assert level(name) == "FULL", name


def to_phase(s, phase, limit=200):
    """Pass priority (decisions answered the plain way, no attacks) until the table reaches ``phase``."""
    for _ in range(limit):
        if s.state.turn.phase == phase and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def kill(s, c):
    act(s, "p1", type="set_damage", card_ids=[c.id], delta=99)
    act(s, s.state.rules.priority or "p1", type="pass_priority")


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0  # (there since before the turn: no summoning sickness)


# -- token copies ------------------------------------------------------------------------------------------------------
def test_wordings():
    for text in ("Create a token that's a copy of it, except it's an artifact in addition to its other types.", "Transform it."):
        assert scripts.parse_effects(text) is None  # (no antecedent outside a trigger: not read)
    found = scripts.parse_effects("Create a tapped and attacking token that's a copy of target creature you control. "
                                  "Sacrifice that token at the beginning of the next end step.")
    assert found is not None and found[0][0]["attacking"] is True and found[0][0]["tapped"] is True
    ex = scripts.parse_effects("Create a token that's a copy of target creature you control, except it's a 2/2 black Zombie in addition "
                               "to its other colors and types.")
    assert ex is not None and ex[0][0]["excepts"][0]["add_subtypes"] == ["Zombie"] and ex[0][0]["excepts"][0]["add_colors"] == ["B"]
    # (an "enters with" rider isn't a copiable value, 707.9: read now as counters the token enters with, test_rules_token_copy_sources.py)
    rider = scripts.parse_effects("Create a token that's a copy of target creature you control, except it enters with an additional "
                                  "+1/+1 counter on it.")
    assert rider is not None and rider[0][0]["excepts"] == [{"enter_counters": [{"counter": "+1/+1", "n": 1}]}]


def test_a_dying_creature_copies_itself_unless_it_is_a_token(cards):
    """Vaultborn Tyrant: "if it's not a token, create a token that's a copy of it, except it's an artifact" (608.2h, 111.12)."""
    s = game(cards, ["Vaultborn Tyrant"])
    tyrant = put(s, "Vaultborn Tyrant")
    kill(s, tyrant)
    drive(s)
    [copy] = tokens(s, "p1")
    got = ch(s, copy)
    assert got.name == "Vaultborn Tyrant" and got.pt == (6, 6) and {"Artifact", "Creature"} <= got.types
    assert s.state.cards[tyrant.id].zone == "p1:graveyard"
    roundtrip(s)
    kill(s, copy)  # the copy is a token: its own death makes nothing (the intervening "if", 603.4)
    drive(s)
    assert tokens(s, "p1") == []
    roundtrip(s)


def test_flamerush_rider_copies_an_attacker_tapped_and_attacking_and_exiles_it_at_end_of_combat(cards):
    s = game(cards, ["Flamerush Rider", "Vaultborn Tyrant"])
    rider, tyrant = put(s, "Flamerush Rider"), put(s, "Vaultborn Tyrant")
    unready(s, rider, tyrant)
    act(s, "p1", type="pass_priority")  # → declare attackers
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": rider.id, "target": "p2"}, {"card_id": tyrant.id, "target": "p2"}])
    responsive(s)  # (each player stops at every object on the stack)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[tyrant.id])  # the other attacker is the target
    for _ in range(6):  # (the trigger resolves; the table stops there while the attackers' damage waits)
        if any(c.is_token and c.zone == "p1:battlefield" for c in s.state.cards.values()):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    [copy] = tokens(s, "p1")
    assert copy.name == "Vaultborn Tyrant" and copy.tapped and copy.attacking is not None  # (508.4: attacking, not "attacked")
    power = sum(ch(s, c).pt[0] for c in (rider, tyrant, copy))
    for _ in range(30):
        if s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 40 - power  # the copy dealt its damage too
    assert copy.id not in s.state.cards  # "Exile the token at end of combat": a token that left the battlefield ceases to exist (111.7)
    roundtrip(s)


# -- transform -------------------------------------------------------------------------------------------------------
def test_foreboding_statue_untaps_and_transforms_it_at_the_end_step(cards):
    s = game(cards, ["Foreboding Statue // Forsaken Thresher"])
    statue = put(s, "Foreboding Statue // Forsaken Thresher")
    act(s, "p1", type="counter", card_ids=[statue.id], kind="omen", delta=3)
    responsive(s)
    to_phase(s, "end")
    drive(s)
    assert s.state.cards[statue.id].face == 1
    assert ch(s, s.state.cards[statue.id]).name == "Forsaken Thresher"
    roundtrip(s)


def test_remove_those_counters_and_transform_it(cards):
    s = game(cards, ["Ludevic's Test Subject // Ludevic's Abomination"])
    sub = put(s, "Ludevic's Test Subject // Ludevic's Abomination")
    unready(s, sub)
    act(s, "p1", type="counter", card_ids=[sub.id], kind="hatchling", delta=4)
    i = next(a.index for a in ch(s, sub).abilities if a.kind == "activated" and "hatchling" in a.text)
    mana(s, U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=sub.id, ability=i)
    drive(s)
    now = s.state.cards[sub.id]
    assert now.face == 1 and not now.counters.get("hatchling")
    assert ch(s, now).name == "Ludevic's Abomination"
    roundtrip(s)


# -- sagas -----------------------------------------------------------------------------------------------------------
def test_a_saga_chapter_with_a_leading_if_is_a_plain_conditional(cards):
    d = scripts.parse_effects("If you control a creature with power 4 or greater, draw two cards.")
    assert d is not None and d[0][0]["do"] == "only_if"  # (checked as the chapter resolves, 608.2c)
    for name in ("The First Iroan Games", "Behold the Unspeakable // Vision of the Unspeakable"):
        assert level(name) == "FULL"


# -- looking at another player's library ---------------------------------------------------------------------------------
@pytest.mark.parametrize("yes", [True, False])
def test_draugr_thought_thief_may_put_the_top_card_into_their_graveyard(cards, yes):
    s = game(cards, ["Draugr Thought-Thief"])
    top = s.state.zones["p2:library"][0]
    cast(s, "Draugr Thought-Thief", U=1, C=2)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards":  # the card looked at: "you may put that card into their graveyard"
            assert d.player == "p1" and [o.card_id for o in d.options] == [top] and d.min_choices == 0
            assert s.view("p2")["rules"]["decision"] is None or "options" not in s.view("p2")["rules"]["decision"]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[top] if yes else [])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    if yes:
        assert s.state.zones["p2:graveyard"][-1] == top and top not in s.state.zones["p2:library"]  # its owner's graveyard (404.1)
    else:
        assert s.state.zones["p2:library"][0] == top
    roundtrip(s)


@pytest.mark.parametrize("keep", [True, False])
def test_gurmag_nightwatch_puts_one_back_and_the_rest_into_the_graveyard(cards, keep):
    """"You may put one of those cards back on top of your library. Put the rest into your graveyard." — declining still sends all three."""
    s = game(cards, ["Gurmag Nightwatch"])
    cast(s, "Gurmag Nightwatch", C=6)
    top3 = list(s.state.zones["p1:library"][:3])
    graveyard = len(s.state.zones["p1:graveyard"])
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            assert d.kind == "choose_cards" and d.min_choices == 0 and [o.card_id for o in d.options] == top3
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[top3[0]] if keep else [])
    assert len(s.state.zones["p1:graveyard"]) == graveyard + (2 if keep else 3)
    assert (s.state.zones["p1:library"][0] == top3[0]) is keep
    roundtrip(s)


def test_ratadrabik_copies_a_dying_legendary_as_a_black_zombie(cards):
    """"except it's not legendary and it's a 2/2 black Zombie in addition to its other colors and types" (707.9b, 707.9d)."""
    s = game(cards, ["Ratadrabik of Urborg", "Mishra, Eminent One"])
    put(s, "Ratadrabik of Urborg")
    mishra = put(s, "Mishra, Eminent One")
    kill(s, mishra)
    drive(s)
    [copy] = tokens(s, "p1")
    got = ch(s, copy)
    assert got.name == "Mishra, Eminent One" and got.pt == (2, 2) and "Zombie" in got.subtypes and "Legendary" not in got.supertypes
    assert got.colors == {"U", "B", "R"} and {"Human", "Artificer"} <= got.subtypes  # (its other colors and types stay: "in addition")
    roundtrip(s)


def test_mishras_warform_is_named_and_built_as_the_text_says_then_sacrificed(cards):
    s = game(cards, ["Mishra, Eminent One", "Sol Ring"])
    mishra, ring = put(s, "Mishra, Eminent One"), put(s, "Sol Ring")
    unready(s, mishra)
    responsive(s)
    act(s, "p1", type="pass_priority")  # → the beginning of combat: the trigger asks for its target
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[ring.id])
        elif tokens(s, "p1"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    [form] = tokens(s, "p1")
    got = ch(s, form)
    assert got.name == "Mishra's Warform" and got.pt == (4, 4) and {"Artifact", "Creature"} <= got.types and "Construct" in got.subtypes
    assert "haste" in got.keywords
    to_phase(s, "end")
    drive(s)
    assert tokens(s, "p1") == []  # "Sacrifice it at the beginning of the next end step"
    roundtrip(s)


def test_chronozoa_makes_two_copies_when_it_dies_with_no_time_counters(cards):
    """"if it had no time counters on it, create two tokens that are copies of it" — as it last existed (608.2h); each copy has vanishing."""
    s = game(cards, ["Chronozoa"])
    zoa = put(s, "Chronozoa")
    act(s, "p1", type="counter", card_ids=[zoa.id], kind="time", delta=-s.state.cards[zoa.id].counters.get("time", 0)) if s.state.cards[zoa.id].counters.get("time") else None
    kill(s, zoa)
    drive(s)
    copies = tokens(s, "p1")
    assert len(copies) == 2 and all(ch(s, c).name == "Chronozoa" for c in copies)
    assert all(c.counters.get("time", 0) == 3 for c in copies)  # (vanishing 3: each token enters with three time counters, 702.63a)
    roundtrip(s)


def test_chronozoa_with_time_counters_leaves_no_copies(cards):
    s = game(cards, ["Chronozoa"])
    zoa = put(s, "Chronozoa")
    act(s, "p1", type="counter", card_ids=[zoa.id], kind="time", delta=1)
    kill(s, zoa)
    drive(s)
    assert tokens(s, "p1") == []  # (the intervening "if", 603.4)


def test_donal_copies_a_flying_creature_spell_as_a_one_one_spirit(cards):
    """"you may copy it, except the copy is a 1/1 Spirit in addition to its other types. Do this only once each turn." (707.10, 707.9b)"""
    s = game(cards, ["Donal, Herald of Wings", "Sphinx of False Conclusions"])
    put(s, "Donal, Herald of Wings")
    cast(s, "Sphinx of False Conclusions", U=2, C=2)
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if any(o.id == "yes" for o in d.options)
                else [o.id for o in d.options][: max(1, d.min_choices)])
    copy = next(c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    got = ch(s, copy)
    assert got.name == "Sphinx of False Conclusions" and got.pt == (1, 1) and {"Sphinx", "Illusion", "Spirit"} <= got.subtypes
    assert "flying" in got.keywords
    original = find(s, "Sphinx of False Conclusions")
    assert s.state.cards[original.id].zone == "p1:battlefield" and ch(s, original).pt == (4, 2)
    roundtrip(s)


@pytest.mark.parametrize("yes", [True, False])
def test_dimensional_infiltrator_may_return_itself_only_if_the_exiled_card_is_a_land(cards, yes):
    """"If it's a land card, you may return this creature to its owner's hand": the gate, then the controller's choice (608.2c, 603.5)."""
    s = game(cards, ["Dimensional Infiltrator"])
    bat = put(s, "Dimensional Infiltrator")
    unready(s, bat)
    top = s.state.zones["p2:library"][0]  # (an Island: Bob's deck is all Islands)
    i = next(a.index for a in ch(s, bat).abilities if a.kind == "activated")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=bat.id, ability=i, targets=["p2"])
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if yes else "no"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[top].zone == "p2:exile"
    assert (s.state.cards[bat.id].zone == "p1:hand") is yes
    roundtrip(s)


# -- kicked cast triggers ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kicked", [0, 1])
def test_sowing_mycospawn_exiles_a_land_only_if_kicked(cards, kicked):
    s = game(cards, ["Sowing Mycospawn"])
    island = put(s, "Island", "battlefield", "p2")
    responsive(s)
    spawn = find(s, "Sowing Mycospawn")
    act(s, "p1", type="move", card_ids=[spawn.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=2, C=6)
    act(s, "p1", type="cast_spell", card_id=spawn.id, kicker=kicked)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = ids if d.kind == "order" else ([i for i in ids if i == island.id] or ids[:1])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert (s.state.cards[island.id].zone == "p2:exile") is bool(kicked)
    roundtrip(s)




# -- statics: spells that can't be countered / can't be cast ---------------------------------------------------------------
@pytest.mark.parametrize("herald", [True, False])
def test_gaeas_herald_makes_every_players_creature_spells_uncounterable(cards, herald):
    """"Creature spells can't be countered." (101.2, 701.6): not only its controller's — Bob's Counterspell fails on Alice's Bears."""
    s = game(cards, ["Grizzly Bears"], ["Counterspell", "Gaea's Herald"])
    if herald:
        put(s, "Gaea's Herald", "battlefield", "p2")
    counter = put(s, "Counterspell", "hand", "p2")
    act(s, "p2", type="set_prefs", response="on")
    bears = put(s, "Grizzly Bears", "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bears.id])
    for _ in range(12):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.cards[bears.id].zone == "p1:battlefield") is herald  # (without it: countered, into the graveyard)
    assert (s.state.cards[bears.id].zone == "p1:graveyard") is not herald
    roundtrip(s)
