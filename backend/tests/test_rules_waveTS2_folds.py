"""-- token stack folds (wave TS2) -- docs/TOKEN_STACKS.md section 9.

N identical triggered abilities that only create tokens (Scute Swarm's landfall, Biowaste Blob's upkeep, Council of Reeds' beginning of
combat) go on the stack as ONE ability "Scute Swarm (×N)" that resolves as the N would, one after another with every player passing
(732.2a), and makes N times the tokens in one creation event; a stack of token copies (707.2) of such a card is one object "Scute Swarm
×4,096" whose members each trigger (603.2c). Anything that could tell the difference refuses the fold (the N triggers stay separate, or the
action is refused when they are too many). Real Oracle text; every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import time

import pytest

from app.game.errors import ActionError
from app.rules import sba
from tests.game_helpers import act
from tests.pod_c_kit import card, ch, mana, put, settle, table, to_hand
from tests.test_rules_pod_adrix import EXTRA as ADRIX_EXTRA
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

EXTRA = [
    *ADRIX_EXTRA,
    real('Biowaste Blob', '{2}{G}{G}', 4, 'Creature — Ooze',
         "Oozes you control get +1/+1.\nAt the beginning of your upkeep, if you control a commander, create a token that's a copy of this "
         "creature.", ('0', '0'), 'G'),
    real('Council of Reeds', '{2}{U}', 3, 'Legendary Creature — Human Scientist Hero',
         'The "legend rule" doesn\'t apply to creatures you control.\nAt the beginning of combat on your turn, if you\'ve cast a noncreature '
         "spell this turn, create a token that's a copy of Council of Reeds.", ('2', '2'), 'U'),
    real('Traveling Chocobo', '{2}{G}', 3, 'Creature — Bird',
         "You may look at the top card of your library any time.\nYou may play lands and cast Bird spells from the top of your library.\n"
         "If a land or Bird you control entering the battlefield causes a triggered ability of a permanent you control to trigger, that "
         "ability triggers an additional time.", ('3', '2'), 'G'),
    real('Ancient Greenwarden', '{4}{G}{G}', 6, 'Creature — Elemental',
         "Reach (This creature can block creatures with flying.)\nYou may play lands from your graveyard.\nIf a land entering causes a "
         "triggered ability of a permanent you control to trigger, that ability triggers an additional time.", ('5', '7'), 'G'),
    real('Explosive Vegetation', '{3}{G}', 4, 'Sorcery',
         'Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.', None, 'G'),
    real('Stifle', '{U}', 1, 'Instant', "Counter target activated or triggered ability. (Mana abilities can't be targeted.)", None, 'U'),
    real('Avenger of Zendikar', '{5}{G}{G}', 7, 'Creature — Elemental',
         "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you "
         "control enters, you may put a +1/+1 counter on each Plant creature you control.", ('5', '5'), 'G'),
    real('Strict Proctor', '{1}{W}', 2, 'Creature — Spirit Cleric',
         "Flying\nWhenever a permanent entering causes a triggered ability to trigger, counter that ability unless its controller pays {2}.",
         ('1', '3'), 'W'),
    real('Giant Growth', '{G}', 1, 'Instant', 'Target creature gets +3/+3 until end of turn.', None, 'G'),
    real('Chatterfang, Squirrel General', '{2}{G}', 3, 'Legendary Creature — Squirrel Warrior',
         "Forestwalk (This creature can't be blocked as long as defending player controls a Forest.)\nIf one or more tokens would be "
         "created under your control, those tokens plus that many 1/1 green Squirrel creature tokens are created instead.\n{B}, Sacrifice "
         "X Squirrels: Target creature gets +X/-X until end of turn.", ('3', '3'), 'G'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def board(cards, swarms, lands=6, mine=(), theirs=(), name="Scute Swarm"):
    """Alice with ``swarms`` permanents named ``name`` (the card and token copies of its printing made by hand), ``lands`` Forests and
    ``mine`` on the battlefield; ramp spells in hand."""
    s = table(cards, [name, "Rampant Growth", "Explosive Vegetation", *mine], theirs, lands=("Forest", 30))
    for x in mine:
        if x not in ("Rampant Growth", "Explosive Vegetation", "Giant Growth", "Stifle"):
            put(s, x)
    put(s, name)
    left = swarms - 1
    while left > 0:
        k = min(left, 100)
        act(s, "p1", type="create_token", player="p1", token={"card_id": card(s, name).card_id}, count=k, stacked=False)
        left -= k
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[f.id for f in forests[:lands]], to={"player": "p1", "zone": "battlefield"})
    return s


def count(s, name="Scute Swarm", pid="p1"):
    """How many permanents of that name (as they are now) the player controls, a stack counting as its members."""
    return sum(s.state.cards[i].quantity for i in s.state.zones[f"{pid}:battlefield"] if ch(s, s.state.cards[i], pid).name == name)


def objects(s, name="Scute Swarm", pid="p1"):
    return [s.state.cards[i] for i in s.state.zones[f"{pid}:battlefield"] if ch(s, s.state.cards[i], pid).name == name]


def triggers(s):
    """The triggered abilities on the stack, bottom first: their names."""
    return [s.state.rules.stack[i].name for i in s.state.zones.get("stack", []) if i in s.state.rules.stack
            and s.state.rules.stack[i].kind == "trigger"]


def ramp(s, spell="Rampant Growth", lands=1):
    """Cast a ramp spell and resolve it: the lands enter; stop with the triggers on the stack (Alice has priority)."""
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    mana(s, G=4)
    c = card(s, spell)
    if not c.zone.endswith(":hand"):
        c = to_hand(s, spell)
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            forests = [o.id for o in d.options if (o.label or "").startswith("Forest")][:lands]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=forests or [o.id for o in d.options][: max(1, d.min_choices)])
            continue
        stack = s.state.zones.get("stack") or []
        if not stack or (stack[-1] in s.state.rules.stack and s.state.rules.stack[stack[-1]].kind == "trigger"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("the spell never resolved")


# -- folding ------------------------------------------------------------------------------------------------------------------------
def test_identical_landfall_triggers_fold_into_one(cards):
    """Five Scute Swarms, six lands: one more land triggers each (603.2c); the five identical triggers go on the stack as ONE ability,
    "Scute Swarm (×5)", which makes five copies (707.2) as it resolves: ten Swarms."""
    s = board(cards, 5)
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×5)"]
    settle(s)
    assert count(s) == 10 and not triggers(s)
    copies = [c for c in objects(s) if c.is_token and c.quantity == 1]
    assert len(copies) == 9 and all(any(a.kind == "triggered" for a in ch(s, c).abilities) for c in copies)
    check(s)


def test_condition_checked_once_as_it_resolves_insects_stack(cards):
    """Four lands then a fifth: fewer than six, so each of 120 Swarms' triggers makes a 1/1 Insect (603.4 / 608.2c: the condition is
    checked as it resolves, the same for each, since no Insect is a land): one creation of 120 Insects, one stack."""
    s = board(cards, 120, lands=4)
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×120)"]
    settle(s)
    insects = objects(s, "Insect")
    assert [c.quantity for c in insects] == [120] and count(s) == 120
    check(s)


def test_copies_stack_with_doublers_and_keep_their_landfall(cards):
    """Adrix and Nev and Primal Vigor: one creation event of 30 copies becomes 120 (616.1f: 2·2·30; the same as 30 events of 4), made as
    one stack "Scute Swarm ×120" of token copies (707.2: the copy effect is on the stack, so each member is a Scute Swarm with landfall).
    The next land triggers all 150 (the stack's members each, 603.2c): one fold of 150, 600 more, one more stack."""
    s = board(cards, 30, mine=["Adrix and Nev, Twincasters", "Primal Vigor"])
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×30)"]
    settle(s)
    assert count(s) == 150
    stack = next(c for c in objects(s) if c.quantity > 1)
    assert stack.quantity == 120 and ch(s, stack).name == "Scute Swarm"
    assert any(a.kind == "triggered" and "Landfall" in a.text for a in ch(s, stack).abilities)
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×150)"]
    settle(s)
    assert count(s) == 750 and sorted(c.quantity for c in objects(s) if c.quantity > 1) == [120, 600]
    check(s)


@pytest.mark.parametrize("multiplier", ["Ancient Greenwarden", "Traveling Chocobo"])
def test_triggering_an_additional_time_doubles_the_fold(cards, multiplier):
    """603.2d: a land entering makes each landfall ability trigger an additional time (Ancient Greenwarden, Traveling Chocobo): ten
    Swarms trigger twenty times, folded into one "(×20)"."""
    s = board(cards, 10, mine=[multiplier])
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×20)"]
    settle(s)
    assert count(s) == 30
    check(s)


def test_two_kinds_fold_as_two_blocks(cards):
    """Three Swarms and two Rampaging Baloths: two groups of identical triggers, each folded; Alice orders the two blocks (603.3b). No
    Beast is a land, so neither block changes the other's result and the order she picks takes nothing away."""
    s = board(cards, 3, mine=["Rampaging Baloths"])
    act(s, "p1", type="create_token", player="p1", token={"card_id": card(s, "Rampaging Baloths").card_id}, count=1, stacked=False)
    ramp(s)
    assert sorted(triggers(s)) == ["Rampaging Baloths (×2)", "Scute Swarm (×3)"]
    settle(s)
    assert count(s) == 6 and count(s, "Beast") == 2
    check(s)


def test_two_lands_at_once_fold_together(cards):
    """Explosive Vegetation: two lands enter at once, two events (603.2c), each triggering each Swarm. The 2×6 instances are identical
    and read nothing of their event, so they fold into one "(×12)": eighteen Swarms (as twelve separate resolutions would make)."""
    s = board(cards, 6)
    ramp(s, "Explosive Vegetation", lands=2)
    assert triggers(s) == ["Scute Swarm (×12)"]
    settle(s)
    assert count(s) == 18
    check(s)


def test_biowaste_blob_upkeep_fold(cards):
    """"At the beginning of your upkeep, if you control a commander, create a token that's a copy of this creature": three Blobs and Krenko
    on the battlefield; the next upkeep folds three triggers (603.4: the condition checked as each triggers and as the fold resolves).
    Blob copies have a static ability, so they never stack, but the creation is still one event."""
    s = board(cards, 3, name="Biowaste Blob")
    commander = card(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[commander.id], to={"player": "p1", "zone": "battlefield"})
    for _ in range(80):
        if s.state.turn.active_player == "p1" and s.state.turn.number > 1 and triggers(s):
            break
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    assert triggers(s) == ["Biowaste Blob (×3)"]
    settle(s)
    assert count(s, "Biowaste Blob") == 6 and all(c.quantity == 1 for c in objects(s, "Biowaste Blob"))
    check(s)


def test_council_of_reeds_legendary_copies_fold(cards):
    """Council of Reeds: "The legend rule doesn't apply to creatures you control" (each copy has it), so folding two beginning-of-combat
    triggers is exact: one creation of two legendary copies (never a stack: 704.5j)."""
    s = board(cards, 2, name="Council of Reeds", mine=["Giant Growth"])
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[card(s, "Council of Reeds").id])
    settle(s)
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    for _ in range(10):
        if triggers(s):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert triggers(s) == ["Council of Reeds (×2)"]
    settle(s)
    assert count(s, "Council of Reeds") == 4 and all(c.quantity == 1 for c in objects(s, "Council of Reeds"))
    check(s)


# -- what stops a fold ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("observer", ["Mister Fantastic, Reed Richards", "Strict Proctor", "Esix, Fractal Bloom",
                                      "Chatterfang, Squirrel General"])
def test_observers_keep_the_triggers_separate(cards, observer):
    """Anything that could tell N resolutions from one: "Whenever one or more tokens you control enter" (once per creation event,
    603.2c), Strict Proctor (one per trigger), Esix ("the first time you would create tokens each turn": only the first event),
    Chatterfang (its "Sacrifice X Squirrels" can't be audited with a stack). The triggers stay separate, exactly as before."""
    s = board(cards, 3, mine=[observer])
    ramp(s)
    assert [t for t in triggers(s) if t.startswith("Scute")] == ["Scute Swarm"] * 3
    settle(s, "No", "Don't")
    assert count(s) > 3  # (Strict Proctor counters what Alice can't pay for)
    check(s)


def test_another_trigger_to_order_keeps_them_separate(cards):
    """603.3b: Avenger of Zendikar's landfall is put on the stack with the Swarms' in an order Alice chooses; folding would force the
    Swarms' to resolve as a block, so they stay separate."""
    s = board(cards, 3, mine=["Avenger of Zendikar"])
    ramp(s)
    assert sorted(triggers(s)) == ["Avenger of Zendikar"] + ["Scute Swarm"] * 3
    settle(s, "No")
    assert count(s) == 6
    check(s)


def test_stifle_counters_one_instance(cards):
    """Bob Stifles "Scute Swarm (×4)": a target is one of the four identical instances, split off first (the other three stay one
    ability above it). Three resolve: seven Swarms."""
    s = board(cards, 4, theirs=["Stifle"])
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})  # every priority a stop (a test device; full control would keep the triggers separate)
    ramp(s)
    folded = s.state.zones["stack"][-1]
    act(s, "p1", type="pass_priority")
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Stifle", "p2").id, targets=[folded])
    assert triggers(s) == ["Scute Swarm", "Scute Swarm (×3)"]
    settle(s)
    assert count(s) == 7
    check(s)


def test_new_observer_before_it_resolves_refuses(cards):
    """Mister Fantastic arrives while "Scute Swarm (×3)" waits: the fold is no longer exact and can't be taken apart, so resolving it is
    refused (pause automation)."""
    s = board(cards, 3, mine=["Mister Fantastic, Reed Richards"])
    fantastic = card(s, "Mister Fantastic, Reed Richards")
    act(s, "p1", type="move", card_ids=[fantastic.id], to={"zone": "hand"})
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×3)"]
    act(s, "p1", type="move", card_ids=[fantastic.id], to={"player": "p1", "zone": "battlefield"})
    with pytest.raises(ActionError, match="resolve them by hand"):
        act(s, "p1", type="pass_priority")
        act(s, "p2", type="pass_priority")


# -- stacks of copies ---------------------------------------------------------------------------------------------------------------
def test_a_split_off_member_still_triggers(cards):
    """Giant Growth on one member of a "Scute Swarm ×120" stack splits it off (it keeps the copy effect, 707.2, and its landfall). The
    next land triggers the 119 and the one (and the 30 others): all fold into one "(×150)"."""
    s = board(cards, 30, mine=["Adrix and Nev, Twincasters", "Primal Vigor", "Giant Growth"])
    ramp(s)
    settle(s)
    stack = next(c for c in objects(s) if c.quantity > 1)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[stack.id])
    settle(s)
    one = s.state.cards[stack.id]
    assert one.quantity == 1 and ch(s, one).name == "Scute Swarm" and sba.power(one, ch(s, one)) == 4
    assert any(a.kind == "triggered" for a in ch(s, one).abilities)
    assert sorted(c.quantity for c in objects(s) if c.quantity > 1) == [119]
    ramp(s)
    assert triggers(s) == ["Scute Swarm (×150)"]
    settle(s)
    assert count(s) == 750
    check(s)


def test_a_copy_stack_refused_when_an_observer_arrives(cards):
    """A stack of 600 Scute Swarm copies and Mister Fantastic: the stack can't be kept exactly and is too big to spread, so the next
    action is refused rather than resolved wrong."""
    s = board(cards, 150, mine=["Adrix and Nev, Twincasters", "Primal Vigor", "Mister Fantastic, Reed Richards"])
    fantastic = card(s, "Mister Fantastic, Reed Richards")
    act(s, "p1", type="move", card_ids=[fantastic.id], to={"zone": "hand"})
    ramp(s)
    settle(s)
    assert max(c.quantity for c in objects(s)) == 600
    with pytest.raises(ActionError, match="Pause automation"):
        act(s, "p1", type="move", card_ids=[fantastic.id], to={"player": "p1", "zone": "battlefield"})
        mana(s, G=2)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rampant Growth").id)


def test_sixty_five_thousand_swarms_play_a_land_fast(cards):
    """Sixteen Swarms, Adrix and Nev, Primal Vigor and Traveling Chocobo: each land makes every Swarm trigger twice and each copy four:
    ×9 per land. 16 → 144 → 1,296 → 11,664 → 104,976 Swarms in a handful of objects, each land in seconds (before: one object per Swarm,
    and 80 Swarms took ~17 s a land)."""
    s = board(cards, 16, mine=["Adrix and Nev, Twincasters", "Primal Vigor", "Traveling Chocobo"])
    took = []
    for expected in (144, 1296, 11664, 104976):
        began = time.perf_counter()
        ramp(s)
        settle(s)
        took.append(time.perf_counter() - began)
        assert count(s) == expected
    assert len(objects(s)) < 40
    assert max(took) < 20, took
    check(s)


# -- token stack folds (playtest choice) -- a player who stops at every priority gets every window, while that many triggers is playable
def test_full_control_keeps_identical_triggers_separate(cards):
    """Bob asked to stop at every priority (full control): Alice's five identical Scute Swarm triggers stay five abilities, so he can act
    between them (732.2b: any player may shorten a shortcut). The result is the same: ten Swarms."""
    s = board(cards, 5)
    act(s, "p2", type="set_prefs", full_control=True)
    ramp(s)
    assert triggers(s) == ["Scute Swarm"] * 5
    settle(s)
    assert count(s) == 10 and not triggers(s)
    check(s)


def test_full_control_still_folds_a_stack_too_big_to_trigger_one_by_one(cards):
    """Past INDIVIDUAL_LIMIT separate triggers would refuse the land outright, so the fold stays even with full control."""
    s = board(cards, 16, mine=["Adrix and Nev, Twincasters", "Primal Vigor", "Traveling Chocobo"])
    ramp(s)
    settle(s)
    ramp(s)
    settle(s)
    assert count(s) == 1296
    act(s, "p2", type="set_prefs", full_control=True)
    ramp(s)
    assert any(t.startswith("Scute Swarm (×") for t in triggers(s))
    settle(s)
    assert count(s) == 11664
    check(s)
