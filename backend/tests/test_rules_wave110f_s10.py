"""Wave 110F session 10: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 702.33c: "As an additional cost to cast this spell, you may pay {1}{G} any number of times." + "3 life plus an additional 3 life for each additional {1}{G} you paid" (Taste of Paradise).
* 704.3, 701.8a, 603.7c: "deals 2 damage to target creature an opponent controls. Destroy all Equipment attached to that creature." + "{2}{R}: Exile the top card of your library. You may play that card this turn. When you play a card this way, ~ deals 2 damage to each player." (Fires of Mount Doom).
* 120.1, 603.4, 603.2: "Whenever combat damage is dealt to you or a planeswalker you control, if this card is in your graveyard, destroy target attacking creature, then put this card on top of your library." (Vengeful Pharaoh).
* 101.4, 701.21a: "Each player sacrifices an artifact, a creature, an enchantment, a land, and a planeswalker of their choice." (Release of Catch // Release): one permanent fills one kind only; a player fills as many kinds as they can.
* 601.2, 609.4b: "you may cast a creature spell from that player's graveyard this turn, and you may spend mana as though it were mana of any color" (Whispersteel Dagger).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import attack
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
)
from tests.test_rules_wave100n_multi import cast
from tests.test_rules_wave34b_activated import activate
from tests.test_rules_wave36a_trigger_words import loyal
from tests.test_rules_wave100f_attached import to_phase
from tests.wave9c_kit import build, check, life, mana, put

EXTRA = [
    real('Whispersteel Dagger', '{2}', 2, 'Artifact — Equipment',
         "Equipped creature gets +2/+0.\nWhenever equipped creature deals combat damage to a player, you may cast a creature spell from that player's graveyard this turn, and you may spend mana as though it were mana of any color to cast that spell.\nEquip {3}", None, ''),
    real('Taste of Paradise', '{2}{G}', 3, 'Sorcery',
         "As an additional cost to cast this spell, you may pay {1}{G} any number of times.\nYou gain 3 life plus an additional 3 life for each additional {1}{G} you paid.", None, 'G'),
    real('Fires of Mount Doom', '{2}{R}', 3, 'Enchantment',
         "When Fires of Mount Doom enters, it deals 2 damage to target creature an opponent controls. Destroy all Equipment attached to that creature.\n{2}{R}: Exile the top card of your library. You may play that card this turn. When you play a card this way, Fires of Mount Doom deals 2 damage to each player.", None, 'R'),
    real('Vengeful Pharaoh', '{2}{B}{B}', 4, 'Creature — Zombie',
         "Deathtouch\nWhenever combat damage is dealt to you or a planeswalker you control, if this card is in your graveyard, destroy target attacking creature, then put this card on top of your library.", ('5', '4'), 'B'),
    real('Test Golem 110F', '{4}', 4, 'Artifact Creature — Golem', '', ('2', '2'), ''),
    real('Test Relic 110F', '{1}', 1, 'Artifact', '', None, ''),
    real('Catch // Release', '{1}{U}{R} // {4}{R}{W}', 6, 'Sorcery // Sorcery',
         "Gain control of target permanent until end of turn. Untap it. It gains haste until end of turn.\nFuse (You may cast one or both halves of this card from your hand.)\n//\n"
         "Each player sacrifices an artifact, a creature, an enchantment, a land, and a planeswalker of their choice.\nFuse (You may cast one or both halves of this card from your hand.)", None, 'RUW')
    | {"layout": "split", "card_faces": [
        {"name": "Catch", "mana_cost": "{1}{U}{R}", "type_line": "Sorcery",
         "oracle_text": "Gain control of target permanent until end of turn. Untap it. It gains haste until end of turn.\nFuse (You may cast one or both halves of this card from your hand)."},
        {"name": "Release", "mana_cost": "{4}{R}{W}", "type_line": "Sorcery",
         "oracle_text": "Each player sacrifices an artifact, a creature, an enchantment, a land, and a planeswalker of their choice.\nFuse (You may cast one or both halves of this card from your hand)."}]},
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", ["Whispersteel Dagger", "Taste of Paradise", "Fires of Mount Doom", "Vengeful Pharaoh", "Catch // Release"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("target,second", [("p2", False), ("p1", False), ("p2", True)])
def test_dagger_casts_one_creature_from_the_damaged_players_graveyard(cards, target, second):
    """Only the damaged player's graveyard (not your own), one creature spell (a second needs its own grant), any color of mana."""
    s = build(cards, ["Whispersteel Dagger", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    dagger, runner = put(s, "Whispersteel Dagger"), put(s, "Grizzly Bears")
    act(s, "p1", type="attach", card_ids=[dagger.id], to=runner.id)
    ours = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.id != runner.id][0]
    theirs = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][:2]
    act(s, "p1", type="move", card_ids=[ours.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[c.id for c in theirs], to={"player": "p2", "zone": "graveyard"})
    attack(s, runner)
    answer(s)
    mana(s, "p1", U=4)
    if target == "p1":
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=ours.id, targets=[])
    else:
        act(s, "p1", type="cast_spell", card_id=theirs[0].id, targets=[])
        answer(s)
        assert s.state.cards[theirs[0].id].zone == "p1:battlefield"
        if second:
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=theirs[1].id, targets=[])
    check(s)


@pytest.mark.parametrize("times", [0, 1, 3])
def test_taste_of_paradise_gains_three_plus_three_per_extra_payment(cards, times):
    """702.33c: each extra {1}{G} paid adds 3 life."""
    s = build(cards, ["Taste of Paradise"])
    mana(s, "p1", G=1 + times, C=2 + times)
    cast(s, "Taste of Paradise", kicker=times)
    answer(s)
    assert life(s, "p1") == 40 + 3 + 3 * times
    check(s)


@pytest.mark.parametrize("equipped", [True, False])
def test_fires_enter_damages_and_destroys_the_equipment_even_if_the_creature_dies(cards, equipped):
    """Equipment attached to the damaged creature is destroyed (SBAs wait: 704.3); the Bear dies; unattached Equipment is untouched."""
    s = build(cards, ["Fires of Mount Doom"], ["Whispersteel Dagger", "Grizzly Bears"])
    bear, dagger = put(s, "Grizzly Bears", "p2"), put(s, "Whispersteel Dagger", "p2")
    if equipped:
        act(s, "p2", type="attach", card_ids=[dagger.id], to=bear.id)
    mana(s, "p1", R=1, C=2)
    cast(s, "Fires of Mount Doom")
    answer(s, [bear.id])
    assert (s.state.cards[bear.id].zone, s.state.cards[dagger.id].zone) == ("p2:graveyard", "p2:graveyard" if equipped else "p2:battlefield")
    check(s)


@pytest.mark.parametrize("play", [True, False])
def test_fires_activation_hurts_each_player_only_when_the_exiled_card_is_played(cards, play):
    """603.7c: playing the exiled card (here a land from the top of the library) triggers 2 damage to each player; not playing it does not."""
    s = build(cards, ["Fires of Mount Doom"])
    fires = put(s, "Fires of Mount Doom")
    mana(s, "p1", R=1, C=2)
    activate(s, "p1", fires, "Exile the top card")
    answer(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert len(exiled) == 1
    if play:
        act(s, "p1", type="play_land", card_id=exiled[0].id)
        answer(s)
    assert (life(s, "p1"), life(s, "p2")) == ((38, 38) if play else (40, 40))
    check(s)


@pytest.mark.parametrize("where,hits", [("p1:graveyard", True), ("p1:hand", False)])
def test_pharaoh_from_the_graveyard_destroys_the_attacker_and_returns_to_the_library_top(cards, where, hits):
    """603.4: only a Pharaoh that is in the graveyard triggers; it destroys the attacker, then goes on top of its owner's library."""
    s = build(cards, ["Vengeful Pharaoh"], ["Grizzly Bears"])
    pharaoh = to_zone(s, "Vengeful Pharaoh", where)
    bear = put(s, "Grizzly Bears", "p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    answer(s)
    assert (s.state.cards[bear.id].zone, s.state.cards[pharaoh.id].zone) == (("p2:graveyard", "p1:library") if hits else ("p2:battlefield", where))
    if hits:
        assert s.state.zones["p1:library"][0] == pharaoh.id
    check(s)


def to_zone(s, name, where):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": where.split(":")[1]})
    return c


def test_pharaoh_also_triggers_when_a_planeswalker_you_control_is_dealt_combat_damage(cards):
    """120.3c: combat damage to your planeswalker counts."""
    s = build(cards, ["Vengeful Pharaoh", "Gideon Jura"], ["Grizzly Bears"])
    pharaoh, jace = to_zone(s, "Vengeful Pharaoh", "p1:graveyard"), loyal(s, "Gideon Jura")
    bear = put(s, "Grizzly Bears", "p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": jace.id}])
    answer(s)
    assert (s.state.cards[bear.id].zone, s.state.cards[pharaoh.id].zone) == ("p2:graveyard", "p1:library")
    check(s)


def _release(s):
    mana(s, "p1", R=1, W=1, C=4)
    cast(s, "Catch // Release", face=1)
    answer(s)


def test_release_each_player_sacrifices_one_permanent_per_type_they_have(cards):
    """701.21a: Alice's Bear and Forest go, her Relic... she has none; Bob's Relic and Golem both go (the Golem fills "creature" since the Relic can fill "artifact")."""
    s = build(cards, ["Catch // Release", "Grizzly Bears", "Grizzly Bears"], ["Test Golem 110F", "Test Relic 110F"], forests=20)
    first = put(s, "Grizzly Bears")
    second = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "battlefield"})
    bears = [first, second]
    forest, golem, relic = put(s, "Forest"), put(s, "Test Golem 110F", "p2"), put(s, "Test Relic 110F", "p2")
    _release(s)
    z = lambda c: s.state.cards[c.id].zone  # noqa: E731
    assert (z(golem), z(relic), z(forest)) == ("p2:graveyard", "p2:graveyard", "p1:graveyard")
    assert sorted(z(b) for b in bears) == ["p1:battlefield", "p1:graveyard"]
    check(s)


def test_release_lone_artifact_creature_is_sacrificed_once(cards):
    """701.21a: an artifact creature fills only one kind: with a second creature, that one goes too."""
    s = build(cards, ["Catch // Release"], ["Test Golem 110F", "Grizzly Bears"], forests=20)
    golem, bear = put(s, "Test Golem 110F", "p2"), put(s, "Grizzly Bears", "p2")
    _release(s)
    assert (s.state.cards[golem.id].zone, s.state.cards[bear.id].zone) == ("p2:graveyard", "p2:graveyard")
    check(s)
