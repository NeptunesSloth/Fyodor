"""-- dive (wave DV) -- the keyword action dive, on synthetic cards with the real printed wording: "Devour 3 / When this creature
enters, if it devoured a creature, it dives. (It can't be blocked until it deals combat damage while attacking.)"

A diving creature can't be blocked until it deals combat damage as an attacking creature (510.2); the effect lasts across turns (611.2a),
ends the moment it connects, not when it deals combat damage as a blocker, and never follows the card through a zone change (400.7). The
intervening if reads what the devourer sacrificed to its own devour (702.82b, 603.4). Also "Target creature dives." on a sorcery and the
plain duration "until it deals combat damage" (any combat damage ends it). Every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, devour, dive
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, to_hand

REAL_TEXT = ("Devour 3 (As this creature enters, you may sacrifice any number of creatures. This creature enters with three +1/+1 counters on it "
             "for each creature sacrificed this way.)\n"
             "When this creature enters, if it devoured a creature, it dives. (It can't be blocked until it deals combat damage while attacking.)")
EXTRA = [
    real("Devouring Diver", "{3}{G}{G}", 5, "Creature — Dinosaur", REAL_TEXT, ("4", "4"), "G"),
    real("Reef Diver", "{2}{U}", 3, "Creature — Merfolk", "When this creature enters, it dives.", ("3", "3"), "U"),
    real("Undertow Lurker", "{2}{U}", 3, "Creature — Merfolk", "When this creature enters, it can't be blocked until it deals combat damage.",
         ("3", "3"), "U"),
    real("Depth Charge", "{U}", 1, "Sorcery", "Target creature dives.", None, "U"),
    # -- group dive (wave DV) -- a group dives: each creature it names, as it resolves (the restriction is locked to them, 611.2c)
    real("School Dive", "{1}{U}", 2, "Sorcery", "Creatures you control dive.", None, "U"),
    real("Paired Plunge", "{U}", 1, "Sorcery", "Up to two target creatures dive.", None, "U"),
    real("Spelled School", "{1}{U}", 2, "Sorcery", "Creatures you control can't be blocked until it deals combat damage while attacking.",
         None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- coverage ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Devouring Diver", "Reef Diver", "Undertow Lurker", "Depth Charge", "School Dive", "Paired Plunge",
                                  "Spelled School"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", coverage.of_card_data(cards.resolve(name)).manual_parts


def test_the_spelled_out_reminder_reads_the_same(cards):
    spelled = dict(cards.resolve("Devouring Diver"), oracle_text="Devour 3\nWhen this creature enters, if it devoured a creature, "
                                                                "it can't be blocked until it deals combat damage while attacking.")
    assert coverage.of_card_data(spelled).level == "FULL"
    for text in ("Each creature you control dives.", "Creatures you control dive.", "Each other creature you control dives.",
                 "Each attacking creature dives.", "Up to two target creatures dive.", "Other creatures you control dive."):
        group = dict(cards.resolve("Depth Charge"), name=f"Group {text}", oracle_text=text)  # -- group dive (wave DV) -- each one dives
        assert coverage.of_card_data(group).level == "FULL", (text, coverage.of_card_data(group).manual_parts)
    assert dive.rewrite("Creatures you control dive.") == "Creatures you control can't be blocked until it deals combat damage while attacking."
    assert dive.rewrite("Each other creature you control dives.") == \
        "Each other creature you control can't be blocked until it deals combat damage while attacking."
    # an ability named for a dive is no action (Dion, Bahamut's Dominant: "Dragonfire Dive — …"), nor is a player
    assert dive.rewrite("Dragonfire Dive — During your turn, Dion has flying.") == "Dragonfire Dive — During your turn, Dion has flying."
    assert dive.rewrite("Each player dives.") == "Each player dives."
    assert dive.rewrite("When ~ enters, if it devoured a creature, it dives.") == \
        "When ~ enters, if it devoured a creature, it can't be blocked until it deals combat damage while attacking."
    assert dive.rewrite("Whenever ~ attacks, ~ dives.") == "Whenever ~ attacks, ~ can't be blocked until it deals combat damage while attacking."
    own_name = dict(cards.resolve("Reef Diver"), oracle_text="Whenever Reef Diver attacks, Reef Diver dives.")  # (the card's own name: "~ dives")
    assert coverage.of_card_data(own_name).level == "FULL"
    assert "dive" in coverage.SUPPORTED_KEYWORD_ACTIONS


# -- helpers -----------------------------------------------------------------------------------------------------------------------------------
def _live(s, name, pid):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":battlefield"))


def _resolve(s, devoured=(), limit=60):
    """Resolve the stack; a devour question sacrifices ``devoured`` (card ids) then says done; any other choice takes its first option."""
    wanted = list(devoured)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = {o.id for o in d.options}
            if devour.DONE in ids:
                pick = next((w for w in wanted if w in ids), devour.DONE)
                if pick != devour.DONE:
                    wanted.remove(pick)
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def _until(s, kind, limit=40):
    """Pass priority (answering nothing else) until a decision of ``kind`` is open."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == kind:
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"no {kind} decision (at {s.state.turn.phase})")


def _attack(s, attacker_id, blocker_id=None, *, attacker="p1", defender="p2"):
    """From the attacker's main phase: attack the defender with one creature; the defender blocks with ``blocker_id`` (None: no block) —
    returns True when that block was declared, False when the table refused it (the attacker can't be blocked). Combat is then played out."""
    _until(s, "declare_attackers")
    act(s, attacker, type="declare_attackers", attackers=[{"card_id": attacker_id, "target": defender}])
    blocked = False
    _until(s, "declare_blockers")
    if blocker_id is not None:
        try:
            act(s, defender, type="declare_blockers", blocks=[{"blocker_id": blocker_id, "attacker_id": attacker_id}])
            blocked = True
        except ActionError:
            pass
    if not blocked:
        act(s, defender, type="declare_blockers", blocks=[])
    to_phase(s, "main2")
    return blocked


def _dive_effects(s):
    return [e for e in s.state.rules.effects if e.duration in (dive.ATTACKING, dive.ANY)]


def _marker(s, card_id):
    return [m for m in s.state.cards[card_id].effects if "blocked" in (m.name or "").lower()]


def _cast(s, name, pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    return c


# -- the real card -----------------------------------------------------------------------------------------------------------------------------
def test_devouring_nothing_it_does_not_dive(cards):
    s = build(cards, ["Devouring Diver", "Grizzly Bears"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[card_named(s, "Grizzly Bears", "p2").id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", G=2, C=3)
    diver = _cast(s, "Devouring Diver")
    _resolve(s)  # (the devour question: sacrifice nothing)
    assert s.state.cards[diver.id].zone == "p1:battlefield" and s.state.cards[bears.id].zone == "p1:battlefield"
    assert s.state.cards[diver.id].counters.get("+1/+1", 0) == 0
    assert not _dive_effects(s) and not _marker(s, diver.id)  # 603.4: it devoured no creature, so the trigger did nothing
    to_phase(s, "main1", turn=3)
    assert _attack(s, diver.id, card_named(s, "Grizzly Bears", "p2").id) is True  # (blocked: a 4/4 into a 2/2)
    assert s.state.players["p2"].life == 40
    check(s)


def test_devouring_a_creature_it_dives_until_it_connects(cards):
    s = build(cards, ["Devouring Diver", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", G=2, C=3)
    diver = _cast(s, "Devouring Diver")
    _resolve(s, devoured=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.cards[diver.id].counters.get("+1/+1") == 3  # 702.82a: three for the one creature
    assert len(_dive_effects(s)) == 1 and _dive_effects(s)[0].duration == dive.ATTACKING
    assert _marker(s, diver.id) and "until it deals combat damage while attacking" in (_marker(s, diver.id)[0].text or "")
    # turn 3: it attacks; Bob's Bears may not block it; it connects for 7
    to_phase(s, "main1", turn=3)
    assert _attack(s, diver.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert s.state.players["p2"].life == 33
    assert not _dive_effects(s) and not _marker(s, diver.id)  # 611.2a: it dealt combat damage while attacking — the effect ended
    # turn 5: the same creature attacks again and can be blocked
    to_phase(s, "main1", turn=5)
    assert _attack(s, diver.id, _live(s, "Grizzly Bears", "p2").id) is True
    assert s.state.players["p2"].life == 33
    check(s)


def test_dive_lasts_across_turns_and_blocking_does_not_end_it(cards):
    s = build(cards, ["Reef Diver"], ["Grizzly Bears", "Grizzly Bears"])
    for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", U=1, C=2)
    diver = _cast(s, "Reef Diver")
    _resolve(s)
    assert len(_dive_effects(s)) == 1
    # Bob's turn 2: his Bears attack, the Diver blocks and kills it — combat damage dealt while blocking doesn't end the dive
    to_phase(s, "main1", turn=2)
    bears = _live(s, "Grizzly Bears", "p2")
    _until(s, "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    _until(s, "declare_blockers")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": diver.id, "attacker_id": bears.id}])
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[diver.id].zone == "p1:battlefield"
    assert len(_dive_effects(s)) == 1 and _marker(s, diver.id)
    # Alice's turn 5 (it never attacked before): still can't be blocked, two turns later (611.2a: not "this turn")
    to_phase(s, "main1", turn=5)
    assert _attack(s, diver.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert s.state.players["p2"].life == 37 and not _dive_effects(s)
    check(s)


def test_leaving_the_battlefield_ends_it_a_new_object_never_dived(cards):
    s = build(cards, ["Reef Diver"], ["Grizzly Bears"])
    act(s, "p2", type="move", card_ids=[card_named(s, "Grizzly Bears", "p2").id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", U=1, C=2)
    diver = _cast(s, "Reef Diver")
    _resolve(s)
    assert _dive_effects(s) and _marker(s, diver.id)
    act(s, "p1", type="move", card_ids=[diver.id], to={"zone": "hand"})  # (bounced by hand: the engine sees the table at its next step)
    act(s, "p1", type="pass_priority")
    assert not _dive_effects(s) and not _marker(s, diver.id)  # 400.7: the effect was about the object that left
    # cast again: the new object's own trigger makes a new effect, about the new object only
    to_phase(s, "main1", turn=3)
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=diver.id)
    _resolve(s)
    assert [e.affected for e in _dive_effects(s)] == [[s.state.rules.object_id(diver.id)]]
    check(s)


def test_target_creature_dives_on_a_sorcery(cards):
    s = build(cards, ["Depth Charge", "Grizzly Bears"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[card_named(s, "Grizzly Bears", "p2").id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", U=1)
    _cast(s, "Depth Charge", targets=[bears.id])
    _resolve(s)
    assert len(_dive_effects(s)) == 1 and _dive_effects(s)[0].affected == [s.state.rules.object_id(bears.id)] and _marker(s, bears.id)
    to_phase(s, "main1", turn=3)
    assert _attack(s, bears.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert s.state.players["p2"].life == 38 and not _dive_effects(s) and not _marker(s, bears.id)
    check(s)


def test_until_it_deals_combat_damage_ends_as_a_blocker_too(cards):
    s = build(cards, ["Undertow Lurker"], ["Grizzly Bears", "Grizzly Bears"])
    for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p1", U=1, C=2)
    lurker = _cast(s, "Undertow Lurker")
    _resolve(s)
    assert len(_dive_effects(s)) == 1 and _dive_effects(s)[0].duration == dive.ANY
    to_phase(s, "main1", turn=2)
    bears = _live(s, "Grizzly Bears", "p2")
    _until(s, "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    _until(s, "declare_blockers")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": lurker.id, "attacker_id": bears.id}])
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert not _dive_effects(s) and not _marker(s, lurker.id)  # it dealt combat damage (as a blocker): the plain form ends
    to_phase(s, "main1", turn=3)
    assert _attack(s, lurker.id, _live(s, "Grizzly Bears", "p2").id) is True
    check(s)


# -- group dive (wave DV) ----------------------------------------------------------------------------------------------------------------------
def _bears_out(s):
    """Every Grizzly Bears onto its owner's battlefield; Alice's, in order."""
    for pid in ("p1", "p2"):
        for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == pid]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]


@pytest.mark.parametrize("spell", ["School Dive", "Spelled School"])
def test_creatures_you_control_dive_each_until_it_connects(cards, spell):
    s = build(cards, [spell, "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears", "Grizzly Bears"])
    a, b = _bears_out(s)
    mana(s, "p1", U=1, C=1)
    _cast(s, spell)
    _resolve(s)
    oid = s.state.rules.object_id
    effects = _dive_effects(s)
    # each creature dived as it resolved: one effect locked to those two objects, not a group read anew (611.2c)
    assert len(effects) == 1 and effects[0].who is None and sorted(effects[0].affected) == sorted([oid(a.id), oid(b.id)])
    assert _marker(s, a.id) and _marker(s, b.id)
    # a creature that comes under Alice's control later never dived
    giant = card_named(s, "Llanowar Elves", "p1")
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="pass_priority")
    assert oid(giant.id) not in _dive_effects(s)[0].affected and not _marker(s, giant.id)
    # turn 3: the first Bears can't be blocked and connect — that one stops diving; the other still dives
    to_phase(s, "main1", turn=3)
    assert _attack(s, a.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert s.state.players["p2"].life == 38
    assert [e.affected for e in _dive_effects(s)] == [[oid(b.id)]] and not _marker(s, a.id) and _marker(s, b.id)
    # turn 5: the first can be blocked again; the second, turns later, still can't — and connecting ends the effect
    to_phase(s, "main1", turn=5)
    assert _attack(s, a.id, _live(s, "Grizzly Bears", "p2").id) is True
    to_phase(s, "main1", turn=7)
    assert _attack(s, b.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert not _dive_effects(s) and not _marker(s, b.id)
    check(s)


def test_a_group_member_that_leaves_stops_diving_the_rest_keep_it(cards):
    s = build(cards, ["School Dive", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    a, b = _bears_out(s)
    mana(s, "p1", U=1, C=1)
    _cast(s, "School Dive")
    _resolve(s)
    act(s, "p1", type="move", card_ids=[a.id], to={"zone": "hand"})  # (bounced: 400.7, what comes back is a new object)
    act(s, "p1", type="pass_priority")
    oid = s.state.rules.object_id
    assert [e.affected for e in _dive_effects(s)] == [[oid(b.id)]] and not _marker(s, a.id) and _marker(s, b.id)
    act(s, "p1", type="move", card_ids=[a.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="pass_priority")
    assert [e.affected for e in _dive_effects(s)] == [[oid(b.id)]] and not _marker(s, a.id)
    to_phase(s, "main1", turn=3)
    assert _attack(s, a.id, _live(s, "Grizzly Bears", "p2").id) is True  # (the new object never dived)
    check(s)


def test_up_to_two_target_creatures_dive(cards):
    s = build(cards, ["Paired Plunge", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    a, b = _bears_out(s)
    mana(s, "p1", U=1)
    _cast(s, "Paired Plunge", targets=[a.id, b.id])
    _resolve(s)
    oid = s.state.rules.object_id
    assert len(_dive_effects(s)) == 1 and sorted(_dive_effects(s)[0].affected) == sorted([oid(a.id), oid(b.id)])
    to_phase(s, "main1", turn=3)
    assert _attack(s, b.id, _live(s, "Grizzly Bears", "p2").id) is False
    assert [e.affected for e in _dive_effects(s)] == [[oid(a.id)]] and _marker(s, a.id)
    check(s)
