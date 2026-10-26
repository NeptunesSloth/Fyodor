"""Wave 110F session 8: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 613.1f, 702.16: "Target creature loses protection from black until end of turn." (Cephalid Snitch): only the black quality goes.
* 704.5g, 120.6: "can't be destroyed by lethal damage unless lethal damage dealt by a single source is marked on it" (Ogre Enforcer).
* 603.4, 118.9: Thunderblade Charge's graveyard trigger pays {2}{R}{R}{R}, then casts the card without paying its mana cost.
* 510.1: Butcher Orgg divides its combat damage among the defending player and/or their creatures; Cunning Giant (unblocked) assigns it all to one creature.
* 613.1f, 113.6: "Cards in graveyards lose all abilities." (Yixlid Jailer): no flashback from a graveyard; permanents on the battlefield keep theirs.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, protection
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import attack
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100f_gear import block
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
    ch,
)
from tests.wave9c_kit import build, card_named, check, life, mana, put

EXTRA = [
    real('Yixlid Jailer', '{1}{B}', 2, 'Creature — Zombie Wizard',
         'Cards in graveyards lose all abilities.', ('2', '1'), 'B'),
    real('Cephalid Snitch', '{1}{U}', 2, 'Creature — Octopus Wizard',
         'Sacrifice this creature: Target creature loses protection from black until end of turn.', ('1', '1'), 'U'),
    real('Test Pro-Black 110F', '{1}{W}', 2, 'Creature — Knight', 'Protection from black', ('2', '2'), 'W'),
    real('Test Pro-Black-Red 110F', '{1}{W}', 2, 'Creature — Knight', 'Protection from black and from red', ('2', '2'), 'W'),
    real('Test Black 110F', '{1}{B}', 2, 'Creature — Zombie', '', ('2', '2'), 'B'),
    real('Test Red 110F', '{1}{R}', 2, 'Creature — Goblin', '', ('2', '2'), 'R'),
    real('Ogre Enforcer', '{3}{R}{R}', 5, 'Creature — Ogre',
         "This creature can't be destroyed by lethal damage unless lethal damage dealt by a single source is marked on it.", ('4', '4'), 'R'),
    real('Shock', '{R}', 1, 'Instant', 'Shock deals 2 damage to any target.', None, 'R'),
    real('Lightning Bolt', '{R}', 1, 'Instant', 'Lightning Bolt deals 3 damage to any target.', None, 'R'),
    real('Test Burn 4 110F', '{2}{R}', 3, 'Instant', 'Test Burn 4 110F deals 4 damage to any target.', None, 'R'),
    real('Thunderblade Charge', '{1}{R}{R}', 3, 'Sorcery',
         'Thunderblade Charge deals 3 damage to any target.\nWhenever one or more creatures you control deal combat damage to a player, if this card is in your graveyard, you may pay {2}{R}{R}{R}. If you do, you may cast it without paying its mana cost.', None, 'R'),
    real('Cunning Giant', '{5}{R}', 6, 'Creature — Giant',
         'If this creature is unblocked, you may have it assign its combat damage to a creature defending player controls.', ('4', '4'), 'R'),
    real('Butcher Orgg', '{4}{R}{R}{R}', 7, 'Creature — Orgg',
         "You may assign this creature's combat damage divided as you choose among defending player and/or any number of creatures they control.", ('6', '6'), 'R'),
    real('Test Pinger 110F', '{1}', 1, 'Artifact', '{0}: This artifact deals 2 damage to target creature.', None, ''),
    real('Test Regen 110F', '{G}', 1, 'Instant', 'Regenerate target creature.', None, 'G'),
    real('Test Flyer 110F', '{1}{W}', 2, 'Creature — Bird', 'Flying', ('1', '1'), 'W'),
]
_BASE.extend(EXTRA)
NAMES = ["Yixlid Jailer", "Cephalid Snitch", "Ogre Enforcer", "Thunderblade Charge", "Cunning Giant", "Butcher Orgg"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("jailer", [False, True])
def test_jailer_blocks_flashback_only_in_graveyards(cards, jailer):
    """613.1f, 702.34a: with the Jailer a graveyard card has no flashback; a flyer on the battlefield keeps flying."""
    s = build(cards, ["Lightning Surge", "Yixlid Jailer", "Test Flyer 110F"], forests=20, islands=20)
    if jailer:
        put(s, "Yixlid Jailer")
    flyer = put(s, "Test Flyer 110F")
    surge = card_named(s, "Lightning Surge")
    act(s, "p1", type="move", card_ids=[surge.id], to={"player": "p1", "zone": "graveyard"})
    assert ("flashback" in ch(s, surge).keywords) != jailer
    assert "flying" in ch(s, flyer).keywords
    mana(s, "p1", R=7)
    if jailer:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=surge.id, targets=["p2"])
    else:
        act(s, "p1", type="cast_spell", card_id=surge.id, targets=["p2"])
    check(s)


@pytest.mark.parametrize("knight", ["Test Pro-Black 110F", "Test Pro-Black-Red 110F"])
def test_snitch_removes_only_protection_from_black(cards, knight):
    """702.16, 613.1f: black no longer sees protection after the sacrifice; red still does when the knight has it (and the effect ends with the turn)."""
    s = build(cards, ["Cephalid Snitch", knight], ["Test Black 110F", "Test Red 110F"], forests=20, islands=20)
    snitch, pro = put(s, "Cephalid Snitch"), put(s, knight)
    black, red = put(s, "Test Black 110F", pid="p2"), put(s, "Test Red 110F", pid="p2")
    prot = lambda src: protection.protected_from(ch(s, pro), ch(s, src))  # noqa: E731
    assert prot(black) and (prot(red) == (knight == "Test Pro-Black-Red 110F"))
    act(s, "p1", type="activate_ability", card_id=snitch.id, ability=0, targets=[pro.id])
    answer(s)
    assert s.state.cards[snitch.id].zone == "p1:graveyard"
    assert not prot(black) and (prot(red) == (knight == "Test Pro-Black-Red 110F"))
    check(s)


@pytest.mark.parametrize("burn,dies", [(["Shock", "Lightning Bolt"], False), (["Shock", "Test Burn 4 110F"], True), (["Test Burn 4 110F"], True)])
def test_enforcer_dies_only_to_lethal_from_one_source(cards, burn, dies):
    """120.6, 704.5g: 5 damage from two sources is marked but none dealt lethal damage alone: it lives; 4 from one source kills it."""
    s = build(cards, ["Ogre Enforcer", "Shock", "Lightning Bolt", "Test Burn 4 110F"], forests=20, islands=20)
    enforcer = put(s, "Ogre Enforcer")
    for name in burn:
        mana(s, "p1", R=3)
        cast(s, name, [enforcer.id])
        answer(s)
    assert (s.state.cards[enforcer.id].zone == "p1:graveyard") == dies
    assert dies or s.state.cards[enforcer.id].damage >= 4
    check(s)


@pytest.mark.parametrize("regen", [False, True])
def test_enforcer_ignores_damage_removed_by_regeneration(cards, regen):
    """120.6, 701.19c: regeneration removes all damage. One source pings 2 + 2 (4, would kill the 4/4; the shield saves it and clears the damage), then 2 more: only 2 is marked, it lives."""
    s = build(cards, ["Ogre Enforcer", "Test Pinger 110F", "Test Regen 110F"], forests=20, islands=20)
    enforcer, pinger = put(s, "Ogre Enforcer"), put(s, "Test Pinger 110F")

    def ping():
        act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=[enforcer.id])
        answer(s)
    ping()
    if regen:
        mana(s, "p1", G=1)
        cast(s, "Test Regen 110F", [enforcer.id])
        answer(s)
    ping()
    assert (s.state.cards[enforcer.id].zone == "p1:graveyard") == (not regen)
    if regen:
        assert s.state.cards[enforcer.id].damage == 0 and not s.state.cards[enforcer.id].damage_by
        ping()
        assert s.state.cards[enforcer.id].zone == "p1:battlefield" and s.state.cards[enforcer.id].damage_by and s.state.cards[enforcer.id].damage == 2
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_thunderblade_charge_recasts_itself_from_the_graveyard(cards, pay):
    """603.4: only from the graveyard; 118.9: paying {2}{R}{R}{R} lets it be cast free, dealing 3 damage; declining leaves it there."""
    s = build(cards, ["Thunderblade Charge", "Grizzly Bears"], forests=20, islands=20)
    bear, charge = put(s, "Grizzly Bears"), card_named(s, "Thunderblade Charge")
    act(s, "p1", type="move", card_ids=[charge.id], to={"player": "p1", "zone": "graveyard"})
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="set_stops", own=["combat_damage"], smart_pass=False)
    attack(s, bear)
    for _ in range(40):  # to the trigger on the stack (combat damage)
        if s.state.zones.get("stack") or s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, "p1", R=5)
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            ids = {o.id for o in d.options}
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"] if "pay" in ids else ["p2"] if "p2" in ids else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == (35 if pay else 38) and s.state.cards[charge.id].zone == "p1:graveyard"
    check(s)


def _combat(s, attacker, blocker=None, use=True, split=None, target=None, remove=False):
    """Attack with ``attacker``; p2 blocks with ``blocker`` (or not); the ability is used or not; the 510.1 answers: ``split`` (id -> damage) or ``target``."""
    act(s, "p1", type="set_stops", own=["end_combat"], smart_pass=False)
    attack(s, attacker)
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase in ("end_combat", "main2") and not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            block(s, *([(blocker, attacker)] if blocker else []))
            if remove:  # the blocker leaves before damage
                act(s, "p2", type="move", card_ids=[blocker.id], to={"player": "p2", "zone": "graveyard"})
        elif d.kind == "confirm":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if use else "no"])
        elif d.kind == "divide":
            act(s, d.player, type="choose", decision_id=d.id, amounts=[split.get(o.id, 0) for o in d.options])
        elif d.kind == "choose_one":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[target])
        else:
            raise AssertionError(d.kind)
    raise AssertionError("combat never ended")


@pytest.mark.parametrize("case", ["split", "declined", "blocked", "blocker_removed"])
def test_butcher_orgg_divides_its_damage(cards, case):
    """510.1 changed by the card: 3 to the player and 3 to a creature (it dies); declined = all 6 to the player; blocked it may still choose (ruling 2004-10-04); blocked with the blocker gone it deals no damage and asks nothing (510.1c)."""
    s = build(cards, ["Butcher Orgg"], ["Grizzly Bears", "Grizzly Bears"], forests=20, islands=20)
    orgg = put(s, "Butcher Orgg")
    bear, other = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][:2]
    for c in (bear, other):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    to_phase(s, "main1", turn=3)
    shares = {"p2": 3, bear.id: 3} if case == "split" else {"p2": 6} if case == "blocked" else None
    _combat(s, orgg, blocker=bear if case in ("blocked", "blocker_removed") else None, use=case != "declined", split=shares, remove=case == "blocker_removed")
    zone = lambda c: s.state.cards[c.id].zone  # noqa: E731
    assert (life(s, "p2"), zone(bear)) == {"split": (37, "p2:graveyard"), "declined": (34, "p2:battlefield"), "blocked": (34, "p2:battlefield"), "blocker_removed": (40, "p2:graveyard")}[case]
    assert zone(other) == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("case", ["unblocked_choose", "unblocked_decline", "blocked"])
def test_cunning_giant_assigns_to_a_creature_only_when_unblocked(cards, case):
    """Cunning Giant: unblocked, all 4 go to the creature chosen (it dies, the player takes none); declined = to the player; blocked: no choice, as usual."""
    s = build(cards, ["Cunning Giant"], ["Grizzly Bears"], forests=20, islands=20)
    giant, bear = put(s, "Cunning Giant"), put(s, "Grizzly Bears", pid="p2")
    to_phase(s, "main1", turn=3)
    _combat(s, giant, blocker=bear if case == "blocked" else None, use=case != "unblocked_decline", target=bear.id)
    assert (life(s, "p2"), s.state.cards[bear.id].zone) == {"unblocked_choose": (40, "p2:graveyard"), "unblocked_decline": (36, "p2:battlefield"),
                                                            "blocked": (40, "p2:graveyard")}[case]
    check(s)
