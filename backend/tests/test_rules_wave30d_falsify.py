"""Wave 30D: false-FULL falsification. Adversarial scenarios on cards the engine reports FULL, real Oracle text
(tests/fixtures/wave30d_falsify_cards.json, from data/cards.sqlite); each checks the replay and a save and a load (CR 2026-09-25).
Every scenario targets the edge of its card most likely to be automated wrongly: an owner that isn't the controller, a rebound
that never resolved, two replacement effects at once, a fresh object, a player other than the first opponent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_multitarget import respond_on
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30d_falsify_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30d", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, a=(), b=(), c=()):
    """Alice, Bob and Carol; each deck is the named cards plus basic lands."""
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in a), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in b), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in c), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", prefer=(), **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s, prefer)


def names(s, zone, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:{zone}"]]


def life(s, pid="p1"):
    return s.state.players[pid].life


def test_displacer_kitten_returns_a_stolen_permanent_to_its_owner(cards):
    """Displacer Kitten: "exile up to one target nonland permanent you control, then return that card to the battlefield under its
    owner's control." (400.7 / 110.2) A creature Alice stole from Bob goes home to Bob, not back to Alice."""
    s = build(cards, ["Displacer Kitten", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Displacer Kitten")
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    assert s.state.cards[bears.id].controller == "p1"
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    settle(s, [bears.id, "Grizzly Bears"])
    assert life(s, "p2") == 37
    got = s.state.cards[bears.id]
    assert got.zone == "p2:battlefield" and got.controller == "p2", (got.zone, got.controller)
    check(s)


def chars(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


def to_phase(s, phase, turn=None, limit=120):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached (its triggers may be on the stack)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def test_helm_of_the_host_copy_is_not_legendary_and_gets_no_counters(cards):
    """Helm of the Host: "create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste."
    (707.2: a copy takes copiable values only — counters and the equipment are not copied; 707.9b the exception.) The token of a legendary
    creature is a non-legendary copy, so the legend rule (704.5j) leaves both; the Helm stays on the original."""
    s = build(cards, ["Helm of the Host", "Kess, Dissident Mage"])
    helm, kess = put(s, "Helm of the Host"), put(s, "Kess, Dissident Mage")
    act(s, "p1", type="counter", card_ids=[kess.id], kind="+1/+1", delta=2)
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=helm.id, ability=1, targets=[kess.id])
    settle(s)
    assert s.state.cards[helm.id].attached_to == kess.id
    to_phase(s, "declare_attackers")  # (the beginning-of-combat trigger has resolved by then)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert [t.name for t in tokens] == ["Kess, Dissident Mage"]
    ch = chars(s, tokens[0])
    assert "Legendary" not in ch.supertypes and "haste" in {k.lower() for k in ch.granted}, (ch.supertypes, ch.granted)
    assert not tokens[0].counters and s.state.cards[kess.id].counters == {"+1/+1": 2}
    assert s.state.cards[kess.id].zone == "p1:battlefield" and s.state.cards[helm.id].attached_to == kess.id
    check(s)


def tokens_of(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:battlefield"] if s.state.cards[c].is_token]


def test_mondrak_and_elspeth_double_twice_and_only_for_their_controller(cards):
    """Mondrak, Glory Dominus and Elspeth, Storm Slayer: "If one or more tokens would be created under your control, twice that many of those
    tokens are created instead." (614.5: each replacement effect applies once, so two of them quadruple: 1 Soldier → 2 → 4; 616.1.) Bob's own
    tokens are never doubled, and a token copy (Helm of the Host, 707.2) is doubled like any other (Mondrak alone: two copies)."""
    s = build(cards, ["Mondrak, Glory Dominus", "Elspeth, Storm Slayer", "Helm of the Host", "Kess, Dissident Mage"], ["Raise the Alarm"])
    put(s, "Mondrak, Glory Dominus")
    elspeth = put(s, "Elspeth, Storm Slayer")
    act(s, "p1", type="activate_ability", card_id=elspeth.id, ability=1)
    respond_on(s)
    act(s, "p1", type="pass_priority")  # (Bob answers with his own tokens)
    to_hand(s, "Raise the Alarm", "p2")
    mana(s, "p2", W=1, C=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Raise the Alarm", "p2").id)
    settle(s)
    assert tokens_of(s) == ["Soldier"] * 4 and tokens_of(s, "p2") == ["Soldier"] * 2, (tokens_of(s), tokens_of(s, "p2"))
    check(s)


def test_mondrak_doubles_a_token_copy(cards):
    s = build(cards, ["Mondrak, Glory Dominus", "Helm of the Host", "Kess, Dissident Mage"])
    put(s, "Mondrak, Glory Dominus")
    helm, kess = put(s, "Helm of the Host"), put(s, "Kess, Dissident Mage")
    mana(s, C=5)
    act(s, "p1", type="activate_ability", card_id=helm.id, ability=1, targets=[kess.id])
    settle(s)
    to_phase(s, "declare_attackers")
    assert tokens_of(s) == ["Kess, Dissident Mage"] * 2, tokens_of(s)
    check(s)


def test_mondrak_indestructible_counter_survives_destroy_and_phyrexian_mana_costs_life(cards):
    """Mondrak: "{1}{W/P}{W/P}, Sacrifice two other artifacts and/or creatures: Put an indestructible counter on Mondrak." (107.4f: {W/P} is
    {W} or 2 life; 122.1b: a permanent with an indestructible counter has indestructible, so Wrath of God's "destroy all creatures"
    doesn't kill it while the sacrificed pair is gone.)"""
    s = build(cards, ["Mondrak, Glory Dominus", "Grizzly Bears", "Llanowar Elves", "Wrath of God"])
    mondrak = put(s, "Mondrak, Glory Dominus")
    bears, wolf = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=mondrak.id, ability=1)
    settle(s)
    assert life(s) == 36 and s.state.cards[mondrak.id].counters == {"indestructible": 1}, (life(s), s.state.cards[mondrak.id].counters)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[wolf.id].zone == "p1:graveyard"
    to_hand(s, "Wrath of God")
    mana(s, W=2, C=2)
    cast(s, "Wrath of God")
    assert s.state.cards[mondrak.id].zone == "p1:battlefield"
    check(s)


def test_ephemerate_that_fizzles_isnt_exiled_for_rebound(cards):
    """Ephemerate: "Rebound (If you cast this spell from your hand, exile it as it resolves. …)" (702.88a). A spell whose only target
    is gone doesn't resolve (608.2b): it goes to the graveyard, so there is no rebound at the next upkeep. (Ephemerate's own ruling.)"""
    s = build(cards, ["Ephemerate", "Grizzly Bears"], ["Lightning Bolt"], forests=20)
    respond_on(s)
    bears = put(s, "Grizzly Bears")
    to_hand(s, "Ephemerate")
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Ephemerate").id, targets=[bears.id])
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert names(s, "graveyard") == ["Grizzly Bears", "Ephemerate"] or sorted(names(s, "graveyard")) == ["Ephemerate", "Grizzly Bears"]
    to_phase(s, "upkeep", turn=3)
    assert s.state.rules.decision is None or s.state.rules.decision.kind != "cast_from_exile"
    settle(s)
    assert "Ephemerate" in names(s, "graveyard") and not names(s, "exile")
    check(s)


def test_ephemerate_returns_a_stolen_creature_to_its_owner_and_rebounds(cards):
    s = build(cards, ["Ephemerate"], ["Grizzly Bears"], forests=20)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    to_hand(s, "Ephemerate")
    mana(s, W=1)
    cast(s, "Ephemerate", targets=[bears.id])
    got = s.state.cards[bears.id]
    assert got.zone == "p2:battlefield" and got.controller == "p2", (got.zone, got.controller)
    assert names(s, "exile") == ["Ephemerate"]  # (cast from hand: exiled as it resolved)
    check(s)


def whip_up(cards, extra=()):
    """Alice: Whip of Erebos and Grizzly Bears (in her graveyard); Whip's ability resolved, so the Bears are back on the battlefield."""
    s = build(cards, ["Whip of Erebos", "Grizzly Bears", *extra], forests=20)
    whip = put(s, "Whip of Erebos")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=2, C=2)
    act(s, "p1", type="activate_ability", card_id=whip.id, ability=1, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    return s, bears


def test_whip_of_erebos_creature_dies_into_exile_and_no_death_trigger(cards):
    """Whip of Erebos: "If it would leave the battlefield, exile it instead of putting it anywhere else." (614.1a) It is never put into
    the graveyard, so an ability that triggers on dying doesn't (Elas il-Kor; Whip's ruling)."""
    s, bears = whip_up(cards, ["Elas il-Kor, Sadistic Pilgrim", "Lightning Bolt"])
    put(s, "Elas il-Kor, Sadistic Pilgrim")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:exile" and "Grizzly Bears" not in names(s, "graveyard")
    assert life(s, "p2") == 40
    check(s)


def test_whip_of_erebos_creature_that_was_flickered_is_a_new_object(cards):
    """Whip's ruling (400.7): a creature exiled and returned (Cloudshift) comes back as a new object with no relation to its previous
    existence: neither the end-step exile nor the "exile instead" applies to it any more."""
    s, bears = whip_up(cards, ["Cloudshift", "Lightning Bolt"])
    to_hand(s, "Cloudshift")
    mana(s, W=1)
    cast(s, "Cloudshift", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    to_phase(s, "main1", turn=3)  # (past Alice's end step, Bob's whole turn and Alice's next untap)
    assert s.state.cards[bears.id].zone == "p1:battlefield", s.state.cards[bears.id].zone
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


def test_whip_of_erebos_creature_is_exiled_at_the_end_step(cards):
    """(the control of the flicker scenario) Left alone, the returned creature has haste and is exiled at the beginning of the next end step."""
    s, bears = whip_up(cards)
    assert "haste" in {k.lower() for k in chars(s, s.state.cards[bears.id]).granted}
    to_phase(s, "main1", turn=3)
    assert s.state.cards[bears.id].zone == "p1:exile"
    check(s)


def test_wishclaw_talisman_gives_it_to_the_chosen_opponent_and_comes_back_when_they_leave(cards):
    """Wishclaw Talisman: "An opponent gains control of this artifact." You choose which opponent while the ability resolves; "if that
    player later leaves the game, you regain control" (its ruling; 800.4a: effects that give that player control end)."""
    s = three(cards, ["Wishclaw Talisman", "Lightning Bolt"])
    talisman = to_hand(s, "Wishclaw Talisman")
    mana(s, B=1, C=1)
    cast(s, "Wishclaw Talisman")
    assert s.state.cards[talisman.id].counters == {"wish": 3}
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=talisman.id, ability=1)
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.player == "p1", (d.player, d.kind)  # (the ability's controller picks the search and the opponent)
        pick = [o.id for o in d.options if "Carol" in o.label or "Lightning Bolt" in o.label or o.id == "p3"] or [d.options[0].id]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=pick[:1])
    settle(s)
    got = s.state.cards[talisman.id]
    assert "Lightning Bolt" in names(s, "hand") and got.counters == {"wish": 2}
    assert (got.owner, got.controller, got.tapped) == ("p1", "p3", True), (got.owner, got.controller, got.tapped)
    act(s, "p3", type="concede")
    got = s.state.cards[talisman.id]
    assert (got.zone, got.controller) == ("p1:battlefield", "p1"), (got.zone, got.controller)
    check(s)


def test_malakir_rebirth_returns_a_stolen_creature_tapped_to_its_owner(cards):
    """Malakir Rebirth: "Until end of turn, that creature gains 'When this creature dies, return it to the battlefield tapped under its
    owner's control.'" The Bears are Bob's, Alice controls them: when they die they come back tapped under Bob's control (110.2), and
    the granted ability is gone with the end of turn (611.2a, 400.7: the new object has no memory of it)."""
    s = build(cards, ["Malakir Rebirth // Malakir Mire", "Lightning Bolt"], ["Grizzly Bears"], forests=20)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    to_hand(s, "Malakir Rebirth // Malakir Mire")
    to_hand(s, "Lightning Bolt")
    mana(s, B=1, R=1)
    cast(s, "Malakir Rebirth // Malakir Mire", face=0, targets=[bears.id])
    assert life(s) == 38
    cast(s, "Lightning Bolt", targets=[bears.id])
    got = s.state.cards[bears.id]
    assert (got.zone, got.controller, got.tapped) == ("p2:battlefield", "p2", True), (got.zone, got.controller, got.tapped)
    assert names(s, "graveyard", "p2") == []
    check(s)


def test_malakir_rebirth_with_its_target_gone_does_nothing(cards):
    """608.2b: with its only target illegal the spell doesn't resolve — no life is lost."""
    s = build(cards, ["Malakir Rebirth // Malakir Mire"], ["Grizzly Bears", "Lightning Bolt"], forests=20)
    respond_on(s)
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Malakir Rebirth // Malakir Mire")
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Malakir Rebirth // Malakir Mire").id, face=0, targets=[bears.id])
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[bears.id])
    settle(s)
    assert life(s) == 40 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_enduring_vitality_comes_back_once_as_an_enchantment(cards):
    """Enduring Vitality: "When this dies, if it was a creature, return it to the battlefield under its owner's control. It's an
    enchantment." (603.4 intervening if, 603.10a: it looks back at the creature it was.) Bob owns it and Alice controls it: it returns to
    Bob. Killed again it is only an enchantment, so it stays dead."""
    s = build(cards, ["Lightning Bolt", "Disenchant"], ["Enduring Vitality"], forests=20)
    vit = put(s, "Enduring Vitality", "p2")
    act(s, "p1", type="set_controller", card_ids=[vit.id], player="p1")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Disenchant")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[vit.id])
    got = s.state.cards[vit.id]
    assert (got.zone, got.controller) == ("p2:battlefield", "p2"), (got.zone, got.controller)
    assert "Creature" not in chars(s, got).types and "Enchantment" in chars(s, got).types
    mana(s, W=1, C=1)
    cast(s, "Disenchant", targets=[vit.id])  # (destroyed as an enchantment: it wasn't a creature, so it stays dead)
    assert s.state.cards[vit.id].zone == "p2:graveyard"
    check(s)


def test_sundering_eruption_lets_the_lands_controller_search_not_the_caster(cards):
    """Sundering Eruption: "Destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield
    tapped, then shuffle." The land's controller (Bob, not Alice) is asked, from Bob's library (a hidden zone); then the "can't block"
    restriction applies to creatures without flying."""
    s = three(cards, ["Sundering Eruption // Volcanic Fissure", "Grizzly Bears"], ["Island"], ["Grizzly Bears"])
    island = put(s, "Island", "p2")
    carol_bears = put(s, "Grizzly Bears", "p3")
    to_hand(s, "Sundering Eruption // Volcanic Fissure")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sundering Eruption // Volcanic Fissure").id, face=0, targets=[island.id])
    seen = []
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        seen.append((d.player, d.kind))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[island.id].zone == "p2:graveyard"
    assert seen and all(p == "p2" for p, _ in seen), seen
    fetched = [c for c in s.state.zones["p2:battlefield"] if s.state.cards[c].name == "Island"]
    assert len(fetched) == 1 and s.state.cards[fetched[0]].tapped and fetched[0] != island.id
    assert not any(s.state.cards[c].name == "Island" for c in s.state.zones["p1:battlefield"])
    assert "cant_block" in "".join(chars(s, carol_bears).imposed) or any("block" in x for x in chars(s, carol_bears).imposed), chars(s, carol_bears).imposed
    check(s)


def test_vorinclex_doubles_my_loyalty_counters_and_halves_an_opponents(cards):
    """Vorinclex, Monstrous Raider: "If you would put one or more counters on a permanent or player, put twice that many of each of those
    kinds of counters … If an opponent would put one or more counters …, they put half that many …, rounded down." A planeswalker enters
    with its loyalty as counters (306.5b, 614.1c): Garruk Wildspeaker (3) comes in with 6 under Alice, and Bob's Jace Beleren (3) with 1
    (its ruling: the replacement applies to the counters a permanent enters with)."""
    s = three(cards, ["Vorinclex, Monstrous Raider", "Garruk Wildspeaker", "Snakeskin Veil"], ["Jace Beleren", "Grizzly Bears", "Snakeskin Veil"])
    vor = put(s, "Vorinclex, Monstrous Raider")
    to_hand(s, "Snakeskin Veil")
    mana(s, G=1)
    cast(s, "Snakeskin Veil", targets=[vor.id])
    assert s.state.cards[vor.id].counters == {"+1/+1": 2}, s.state.cards[vor.id].counters  # (one counter, put by Alice: twice)
    to_hand(s, "Garruk Wildspeaker")
    mana(s, G=2, C=2)
    cast(s, "Garruk Wildspeaker")
    garruk = card_named(s, "Garruk Wildspeaker")
    assert garruk.zone == "p1:battlefield" and garruk.counters.get("loyalty") == 6, (garruk.zone, garruk.counters)
    to_phase(s, "main1", turn=2)
    to_hand(s, "Jace Beleren", "p2")
    mana(s, "p2", U=2, C=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Jace Beleren", "p2").id)
    settle(s)
    jace = card_named(s, "Jace Beleren", "p2")
    assert jace.zone == "p2:battlefield" and jace.counters.get("loyalty") == 1, (jace.zone, jace.counters)
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Snakeskin Veil", "p2")
    mana(s, "p2", G=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Snakeskin Veil", "p2").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].counters == {}, s.state.cards[bears.id].counters  # (Bob's one counter: half of 1, rounded down, is none)
    check(s)


@pytest.mark.parametrize(("answer", "counters"), [("yes", 4), ("no", 3)])
def test_two_counter_replacements_ask_for_their_order(cards, answer, counters):
    """The Earth Crystal (twice that many) and Ozolith, the Shattered Spire (that many plus one) on Tireless Tracker's one counter: its
    controller chooses the order (616.1): (1 + 1) × 2 = 4 or 1 × 2 + 1 = 3 — never a silent default."""
    s = build(cards, ["Tireless Tracker", "The Earth Crystal", "Ozolith, the Shattered Spire", "Forest"], forests=20)
    tracker = put(s, "Tireless Tracker")
    put(s, "The Earth Crystal")
    put(s, "Ozolith, the Shattered Spire")
    act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)  # landfall: investigate
    settle(s)
    clue = next(c for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=clue.id, ability=0)  # "Whenever you sacrifice a Clue, put a +1/+1 counter on this creature."
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {"yes", "no"}, d
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    settle(s)
    assert s.state.cards[tracker.id].counters == {"+1/+1": counters}
    check(s)


@pytest.mark.parametrize("foretold", [False, True])
def test_delayed_blast_fireball_hits_every_opponent_for_more_when_cast_from_exile(cards, foretold):
    """Delayed Blast Fireball: "deals 2 damage to each opponent and each creature they control. If this spell was cast from exile, it deals
    5 damage … instead." (601.2a; its ruling: from exile for any reason.) With three players both opponents and both their creatures take it;
    Alice's own creature takes nothing."""
    s = three(cards, ["Delayed Blast Fireball", "Grizzly Bears", "Twisted Abomination"], ["Twisted Abomination"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    bob, carol = put(s, "Twisted Abomination", "p2"), put(s, "Grizzly Bears", "p3")
    fireball = to_hand(s, "Delayed Blast Fireball")
    if foretold:
        mana(s, C=2)
        act(s, "p1", type="activate_ability", card_id=fireball.id, ability=1)
        assert s.state.cards[fireball.id].zone == "p1:foretell"
        to_phase(s, "main1", turn=4)
        mana(s, R=2, C=4)
    else:
        mana(s, R=2, C=1)
    cast(s, "Delayed Blast Fireball")
    dmg = 5 if foretold else 2
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == (40 - dmg, 40 - dmg, 40)
    assert s.state.cards[carol.id].zone == "p3:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    assert s.state.cards[bob.id].zone == ("p2:graveyard" if foretold else "p2:battlefield")  # (a 5/3: 2 damage doesn't kill it, 5 does)
    check(s)


def make_token(s, pid, name, type_line, pt="1/1", text="", colors=()):
    """A token made at the table (the manual way), returned as the new card's id."""
    before = set(s.state.cards)
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text, "colors": list(colors)})
    return next(c for c in s.state.cards if c not in before)


def test_lathril_needs_ten_other_untapped_elves(cards):
    """Lathril, Blade of the Elves: "{T}, Tap ten untapped Elves you control: Each opponent loses 10 life and you gain 10 life." Lathril is
    tapped by {T} (602.5a), so he can't also be one of the ten (118.3: an untapped Elf): nine other Elves are not enough, ten are, and
    every opponent loses the life. (The tokens and Lathril lost their summoning sickness by Alice's next turn: 302.6.)"""
    s = three(cards, ["Lathril, Blade of the Elves"])
    lathril = put(s, "Lathril, Blade of the Elves")
    elves = [make_token(s, "p1", "Elf Warrior", "Token Creature — Elf Warrior", colors="G") for _ in range(9)]
    to_phase(s, "main1", turn=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=lathril.id, ability=2)
    assert not s.state.cards[lathril.id].tapped and not any(s.state.cards[e].tapped for e in elves)
    elves.append(make_token(s, "p1", "Elf Warrior", "Token Creature — Elf Warrior", colors="G"))  # (new this turn: tapping it needs no {T}, 302.6)
    act(s, "p1", type="activate_ability", card_id=lathril.id, ability=2)
    settle(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (50, 30, 30)
    assert s.state.cards[lathril.id].tapped and all(s.state.cards[e].tapped for e in elves)
    check(s)


def test_alchemists_talent_counts_only_spells_paid_with_treasure_mana(cards):
    """Alchemist's Talent, level 3: "Whenever you cast a spell, if mana from a Treasure was spent to cast it, this Class deals damage equal
    to that spell's mana value to each opponent." (603.4 intervening if, 601.2h.) Paid from the pool (mana from no Treasure) nothing
    happens; paid by sacrificing a Treasure it hits both opponents."""
    s = three(cards, ["Alchemist's Talent", "Lightning Bolt", "Lightning Bolt"])
    talent = to_hand(s, "Alchemist's Talent")
    mana(s, R=1, C=3)
    cast(s, "Alchemist's Talent")
    assert [s.state.cards[c].tapped for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Treasure"] == [True, True]
    mana(s, R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=talent.id, ability=1)  # {1}{R}: Level 2
    settle(s)
    mana(s, R=1, C=4)
    act(s, "p1", type="activate_ability", card_id=talent.id, ability=3)  # {4}{R}: Level 3
    settle(s)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)  # (a land-style payment: the pool, no Treasure)
    cast(s, "Lightning Bolt", targets=["p3"])
    assert (life(s, "p2"), life(s, "p3")) == (40, 37), (life(s, "p2"), life(s, "p3"))
    to_phase(s, "main1", turn=4)  # (the Treasures untap)
    bolt = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.zone in ("p1:library", "p1:hand")][0]
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # nothing in the pool: a Treasure is sacrificed for {R}
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 1
    assert (life(s, "p2"), life(s, "p3")) == (36, 36), (life(s, "p2"), life(s, "p3"))  # Bolt's 3 to Bob, and the Class's 1 to each
    check(s)


def attack(s, *pairs, turn=None):
    """Alice declares these attackers ((card, target) pairs) and combat runs to the second main phase unblocked."""
    if turn:
        to_phase(s, "declare_attackers", turn=turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])
    to_phase(s, "main2")


def test_ragavan_exiles_from_the_damaged_players_library_and_a_land_cant_be_cast(cards):
    """Ragavan, Nimble Pilferer: "Whenever Ragavan deals combat damage to a player, create a Treasure token and exile the top card of that
    player's library. Until end of turn, you may cast that card." With three players it is the damaged player's library (Carol's, not
    Bob's); Alice casts Carol's Lightning Bolt with the Treasure; a land (Ragavan's ruling) can't be cast, so it stays in exile."""
    s = three(cards, ["Ragavan, Nimble Pilferer"], ["Lightning Bolt"], ["Lightning Bolt"])
    ragavan = put(s, "Ragavan, Nimble Pilferer")
    to_phase(s, "declare_attackers", turn=4)  # (Carol has drawn for her turn: the Bolt goes on top of her library now)
    carol_bolt = card_named(s, "Lightning Bolt", "p3")
    act(s, "p3", type="move", card_ids=[carol_bolt.id], to={"player": "p3", "zone": "library"}, position="top")
    attack(s, (ragavan, "p3"))
    assert life(s, "p3") == 38 and not names(s, "exile", "p2")
    assert s.state.cards[carol_bolt.id].zone == "p3:exile"
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 1
    act(s, "p1", type="cast_spell", card_id=carol_bolt.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[carol_bolt.id].zone == "p3:graveyard"  # (to its owner's graveyard)
    check(s)


def test_ragavan_with_a_land_on_top_exiles_it_and_still_makes_the_treasure(cards):
    s = three(cards, ["Ragavan, Nimble Pilferer"])
    ragavan = put(s, "Ragavan, Nimble Pilferer")
    to_phase(s, "declare_attackers", turn=4)
    top = s.state.zones["p2:library"][0]
    assert s.state.cards[top].name == "Island"
    attack(s, (ragavan, "p2"))
    assert s.state.cards[top].zone == "p2:exile" and life(s, "p2") == 38
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 1
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=top)  # (a land can't be played from there: Ragavan says "cast")
    check(s)


def test_face_breaker_makes_one_treasure_per_damage_step_not_per_creature(cards):
    """Professional Face-Breaker: "Whenever one or more creatures you control deal combat damage to a player, create a Treasure token."
    (603.2c) Two attackers dealing damage together to the same player make one Treasure; a first striker that deals its damage in an
    earlier combat damage step (510.4) makes another one."""
    s = build(cards, ["Professional Face-Breaker", "Grizzly Bears"], forests=20)
    breaker, bears = put(s, "Professional Face-Breaker"), put(s, "Grizzly Bears")
    swift = s.state.cards[make_token(s, "p1", "Swift Elf", "Token Creature — Elf", "2/2", "First strike")]

    def treasures():
        return sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield")

    attack(s, (breaker, "p2"), (bears, "p2"), turn=3)
    assert life(s, "p2") < 40 and treasures() == 1, (life(s, "p2"), treasures())
    before = life(s, "p2")
    attack(s, (swift, "p2"), (bears, "p2"), turn=5)
    assert before - life(s, "p2") == 4 and treasures() == 3, (life(s, "p2"), treasures())  # (the first strike step, then the regular one)
    check(s)


def test_lotho_counts_spells_cast_before_it_and_each_players_own_second_spell(cards):
    """Lotho, Corrupt Shirriff: "Whenever a player casts their second spell each turn, you lose 1 life and create a Treasure token."
    (Its ruling: spells cast before Lotho count.) Alice's first spell comes before Lotho is there; Bob's second spell then triggers it
    (his first doesn't); Alice's second triggers it; her third and Bob's third don't."""
    s = build(cards, ["Lotho, Corrupt Shirriff", *["Lightning Bolt"] * 3], ["Lightning Bolt"] * 3, forests=20)
    respond_on(s)
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt"]
    mine, theirs = [c for c in bolts if c.owner == "p1"], [c for c in bolts if c.owner == "p2"]
    for c in mine + theirs:
        act(s, c.owner, type="move", card_ids=[c.id], to={"zone": "hand"})

    def treasures():
        return sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield")

    def bolt(c, target):
        mana(s, c.owner, R=1)
        while s.state.rules.priority != c.owner:  # (the other player passes until the caster has priority)
            act(s, s.state.rules.priority, type="pass_priority")
        act(s, c.owner, type="cast_spell", card_id=c.id, targets=[target])

    bolt(mine[0], "p2")  # Alice's first spell, before Lotho
    put(s, "Lotho, Corrupt Shirriff")
    bolt(theirs[0], "p2")  # Bob's first
    assert (life(s, "p1"), treasures()) == (40, 0)
    bolt(theirs[1], "p2")  # Bob's second: Lotho triggers
    settle(s)
    assert (life(s, "p1"), treasures()) == (39, 1), (life(s, "p1"), treasures())
    bolt(mine[1], "p2")  # Alice's second
    settle(s)
    assert (life(s, "p1"), treasures()) == (38, 2), (life(s, "p1"), treasures())
    bolt(mine[2], "p2")  # her third
    bolt(theirs[2], "p2")  # Bob's third
    settle(s)
    assert (life(s, "p1"), treasures()) == (38, 2), (life(s, "p1"), treasures())
    check(s)


def test_crypt_ghast_adds_black_for_a_nonbasic_land_with_the_swamp_type(cards):
    """Crypt Ghast: "Whenever you tap a Swamp for mana, add an additional {B}." A Swamp is any land with the subtype (205.3i, 305.6):
    Underground Sea (Island Swamp) tapped for {B} makes {B}{B}. Alice pays {1}{B}{B} for Murder with the Sea and one Forest only."""
    s = build(cards, ["Crypt Ghast", "Underground Sea", "Murder"], ["Grizzly Bears"], forests=20)
    put(s, "Crypt Ghast")
    put(s, "Underground Sea")
    bears = put(s, "Grizzly Bears", "p2")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Murder")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[card_named(s, "Underground Sea").id].tapped and s.state.cards[forest.id].tapped
    check(s)


def test_crypt_ghast_adds_only_for_a_swamp(cards):
    """A Forest tapped for {G} adds nothing extra; a Swamp tapped for {B} makes {B}{B} (the trigger resolves at once, 605.5a)."""
    s = build(cards, ["Crypt Ghast", "Swamp"], forests=20)
    put(s, "Crypt Ghast")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    swamp = card_named(s, "Swamp")
    for c in (forest, swamp):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 1}, s.state.players["p1"].mana
    act(s, "p1", type="activate_ability", card_id=swamp.id, ability=0)
    assert s.state.players["p1"].mana == {"G": 1, "B": 2}, s.state.players["p1"].mana
    check(s)


def lands(s, pid="p1"):
    return [c for c in s.state.zones[f"{pid}:battlefield"] if "Land" in chars(s, s.state.cards[c]).types]


def swarm_game(cards, n_lands):
    """Alice has Scute Swarm and ``n_lands - 1`` Forests on the battlefield, and one more Forest in hand to play."""
    s = build(cards, ["Scute Swarm", "Lightning Bolt"], ["Lightning Bolt"], forests=20)
    swarm = put(s, "Scute Swarm")
    for f in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][: n_lands - 1]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    return s, swarm


@pytest.mark.parametrize(("n_lands", "copies"), [(5, 0), (6, 1)])
def test_scute_swarm_copies_itself_only_from_the_sixth_land(cards, n_lands, copies):
    """Scute Swarm: "Landfall — … create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of
    this creature instead." The land that triggered it counts (it is already on the battlefield, 603.6a): five lands in all give an Insect,
    six a copy of the Swarm."""
    s, swarm = swarm_game(cards, n_lands)
    f = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone in ("p1:library", "p1:hand"))
    act(s, "p1", type="move", card_ids=[f.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=f.id)
    settle(s)
    assert len(lands(s)) == n_lands
    assert names(s, "battlefield").count("Scute Swarm") == 1 + copies and names(s, "battlefield").count("Insect") == 1 - copies, names(s, "battlefield")
    check(s)


def test_scute_swarm_copy_survives_the_swarm_dying_in_response(cards):
    """The trigger doesn't need the Swarm to still be there: it copies the creature as it last existed (608.2h, 707.2), and the six
    lands are counted as it resolves."""
    s, swarm = swarm_game(cards, 6)
    respond_on(s)
    f = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone in ("p1:library", "p1:hand"))
    act(s, "p1", type="move", card_ids=[f.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=f.id)
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[swarm.id])
    settle(s)
    assert s.state.cards[swarm.id].zone == "p1:graveyard"
    assert names(s, "battlefield") .count("Scute Swarm") == 1 and "Insect" not in names(s, "battlefield"), names(s, "battlefield")
    check(s)


def test_plaguebearer_targets_the_creature_whose_mana_value_is_x(cards):
    """Plaguebearer: "{X}{X}{B}: Destroy target nonblack creature with mana value X." (107.3g: X is the chosen value in the cost.) A token
    has mana value 0 (202.3), so X = 0 destroys it but not the Bears, and X = 2 the Bears but not the token or the black Zombie."""
    s = build(cards, ["Plaguebearer"], ["Grizzly Bears", "Dregscape Zombie"], forests=20)
    pb = put(s, "Plaguebearer")
    bears, zombie = put(s, "Grizzly Bears", "p2"), put(s, "Dregscape Zombie", "p2")
    goblin = s.state.cards[make_token(s, "p2", "Goblin", "Token Creature — Goblin", "1/1")]
    to_phase(s, "main1", turn=3)  # (no longer summoning sick)

    def kill(x, target):
        mana(s, B=1, C=2 * x)
        act(s, "p1", type="activate_ability", card_id=pb.id, ability=0, targets=[target.id], x_value=x)
        settle(s)

    for x, target in ((0, bears), (2, goblin), (2, zombie)):
        with pytest.raises(ActionError):
            kill(x, target)
        act(s, "p1", type="clear_mana", player="p1")
    kill(0, goblin)
    assert goblin.id not in s.state.cards or s.state.cards[goblin.id].zone != "p2:battlefield"
    kill(2, bears)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[zombie.id].zone == "p2:battlefield"
    check(s)


def test_greater_good_draws_the_sacrificed_creatures_last_known_power(cards):
    """Greater Good: "Sacrifice a creature: Draw cards equal to the sacrificed creature's power, then discard three cards." The Bears were
    pumped by Giant Growth (+3/+3 until end of turn): they die as a 5/5, and that last-known power (608.2h) is what counts."""
    s = build(cards, ["Greater Good", "Grizzly Bears", "Giant Growth"], forests=20)
    gg, bears = put(s, "Greater Good"), put(s, "Grizzly Bears")
    to_hand(s, "Giant Growth")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[bears.id])
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=gg.id, ability=0)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + 5 - 3, (hand, len(s.state.zones["p1:hand"]))
    check(s)


@pytest.mark.parametrize(("victim", "drawn"), [("Kess, Dissident Mage", 3), ("Grizzly Bears", 2)])
def test_nasty_end_asks_if_the_sacrificed_creature_was_legendary(cards, victim, drawn):
    """Nasty End: "If the sacrificed creature was legendary, draw three cards instead." (608.2h: it looks at the creature as it was.)"""
    s = build(cards, ["Nasty End", victim], forests=20)
    put(s, victim)
    to_hand(s, "Nasty End")
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=1, C=1)
    cast(s, "Nasty End")
    assert len(s.state.zones["p1:hand"]) == hand - 1 + drawn, (hand, len(s.state.zones["p1:hand"]))
    check(s)


def test_dina_gains_the_last_known_power_of_the_sacrificed_creature(cards):
    """Dina, Soul Steeper: "{1}, Sacrifice another creature: Dina gets +X/+0 until end of turn, where X is the sacrificed creature's power."
    The Bears are a 5/5 under Giant Growth when they are sacrificed."""
    s = build(cards, ["Dina, Soul Steeper", "Grizzly Bears", "Giant Growth"], forests=20)
    dina, bears = put(s, "Dina, Soul Steeper"), put(s, "Grizzly Bears")
    base = pt(s, "Dina, Soul Steeper")[0]
    to_hand(s, "Giant Growth")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[bears.id])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=dina.id, ability=1)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert pt(s, "Dina, Soul Steeper")[0] == base + 5, (base, pt(s, "Dina, Soul Steeper"))
    check(s)


def test_metamorph_copy_of_a_walker_enters_with_no_counters_and_dies_without_thopters(cards):
    """Phyrexian Metamorph copying Hangarback Walker (3 counters on it): "enters with X +1/+1 counters" — X is 0 for a permanent that wasn't
    cast with an X (107.3f), and counters aren't copiable values (707.2), so the copy is a 0/0 artifact creature that dies (704.5f); its
    "create a Thopter for each +1/+1 counter on this creature" counts the zero it last had. {U/P} paid with 2 life (107.4f)."""
    s = build(cards, ["Phyrexian Metamorph", "Hangarback Walker"], forests=20)
    walker = put(s, "Hangarback Walker")
    act(s, "p1", type="counter", card_ids=[walker.id], kind="+1/+1", delta=3)
    to_hand(s, "Phyrexian Metamorph")
    mana(s, C=3)
    cast(s, "Phyrexian Metamorph", prefer=("Hangarback Walker", "yes"))
    assert life(s) == 38, life(s)
    meta = card_named(s, "Phyrexian Metamorph")
    assert meta.zone == "p1:graveyard", meta.zone
    assert names(s, "battlefield").count("Thopter") == 0 and s.state.cards[walker.id].counters == {"+1/+1": 3}
    check(s)


def test_metamorph_copy_is_an_artifact_in_addition_and_sees_an_opponents_creature(cards):
    """Metamorph "may have this creature enter as a copy of any artifact or creature on the battlefield": Bob's Bears (a creature of
    another player), "except it's an artifact in addition to its other types" (707.9b): an artifact creature named Grizzly Bears."""
    s = build(cards, ["Phyrexian Metamorph"], ["Grizzly Bears"], forests=20)
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Phyrexian Metamorph")
    mana(s, U=1, C=3)
    cast(s, "Phyrexian Metamorph", prefer=("Grizzly Bears", "yes"))
    meta = card_named(s, "Phyrexian Metamorph")
    ch = chars(s, meta)
    assert meta.zone == "p1:battlefield" and ch.name == "Grizzly Bears" and {"Artifact", "Creature"} <= set(ch.types), (meta.zone, ch.name, ch.types)
    assert life(s) == 40  # (paid with {U})
    check(s)


def test_anim_pakal_makes_its_gnomes_attack_whom_alice_chooses_even_if_it_left(cards):
    """Anim Pakal, Thousandth Moon (its rulings): the controller chooses which player each Gnome token enters attacking (508.4, 3-player), and
    if Anim Pakal has left when the ability resolves you still create Gnomes — as many as the +1/+1 counters it had when it was last on the
    battlefield (608.2h), with no new counter put on it. BUG fixed in wave 30D: one question covered every token (token_grammar /
    refused_zones / looking ``enter_attacking``), so the Gnomes could not be split between Bob and Carol; now one question per token."""
    s = three(cards, ["Anim Pakal, Thousandth Moon", "Grizzly Bears"], ["Murder"])
    respond_on(s)
    pakal, bears = put(s, "Anim Pakal, Thousandth Moon"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[pakal.id], kind="+1/+1", delta=2)
    to_phase(s, "declare_attackers", turn=4)
    to_hand(s, "Murder", "p2")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    mana(s, "p2", B=2, C=1)
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Murder", "p2").id, targets=[pakal.id])
    picks = ["p3", "p2"]
    for _ in range(12):  # (the Murder resolves first; then the trigger asks whom each Gnome attacks: Alice picks Carol, then Bob)
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p1" and d.kind == "choose_one", (d.player, d.kind)
            pick = picks.pop(0)
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[pakal.id].zone == "p1:graveyard"
    gnomes = [c for c in s.state.cards.values() if c.name == "Gnome" and c.zone == "p1:battlefield"]
    assert len(gnomes) == 2 and all(g.tapped for g in gnomes), len(gnomes)
    assert sorted(g.attacking.id for g in gnomes) == ["p2", "p3"], [g.attacking for g in gnomes]
    check(s)


def bolt_from(s, c, target):
    """``c`` (a Lightning Bolt in its owner's hand) is cast at ``target`` once its owner has priority (the other players pass), paid from the pool."""
    mana(s, c.owner, R=1)
    while s.state.rules.priority != c.owner:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, c.owner, type="cast_spell", card_id=c.id, targets=[target])


def all_bolts(s):
    out = {}
    for c in s.state.cards.values():
        if c.name == "Lightning Bolt":
            out.setdefault(c.owner, []).append(c)
    for owner, cs in out.items():
        for c in cs:
            act(s, owner, type="move", card_ids=[c.id], to={"zone": "hand"})
    return out


def test_gisela_doubles_damage_to_my_opponents_and_halves_damage_to_me(cards):
    """Gisela, Blade of Goldnight: "If a source would deal damage to an opponent or a permanent an opponent controls, that source deals double
    that damage … If a source would deal damage to you or a permanent you control, prevent half that damage, rounded up." (614.1, 615.1)
    Any source — Bob's own Bolt at Alice does 3 - 2 = 1; Alice's Bolt at Bob or at Carol does 6; a Bolt at Alice's Bears does 1 (they live)."""
    s = three(cards, ["Gisela, Blade of Goldnight", "Grizzly Bears", "Lightning Bolt"], ["Lightning Bolt", "Lightning Bolt"], ["Lightning Bolt"])
    respond_on(s)
    put(s, "Gisela, Blade of Goldnight")
    mine = put(s, "Grizzly Bears")
    bolts = all_bolts(s)
    bolt_from(s, bolts["p1"][0], "p2")
    settle(s)
    assert life(s, "p2") == 34, life(s, "p2")
    bolt_from(s, bolts["p3"][0], "p3")  # Carol bolts herself: she is Alice's opponent too
    settle(s)
    assert life(s, "p3") == 34, life(s, "p3")
    bolt_from(s, bolts["p2"][0], "p1")
    settle(s)
    assert life(s, "p1") == 39, life(s, "p1")
    bolt_from(s, bolts["p2"][1], mine.id)
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[mine.id].damage == 1, (s.state.cards[mine.id].zone, s.state.cards[mine.id].damage)
    check(s)


@pytest.mark.parametrize(("answer", "dealt"), [("yes", 2), ("no", 3)])  # ("yes": Gisela first)
def test_solphim_against_gisela_lets_the_damaged_player_order_double_and_prevent(cards, answer, dealt):
    """Alice's Solphim (double noncombat damage to an opponent) against Bob's Gisela (prevent half of the damage to him, rounded up): both
    change the damage to Bob, so Bob chooses the order (616.1, Gisela's ruling): double first 3 → 6 → 3 left after preventing half;
    prevent first 3 → 1 left (half, rounded up, is 2) → doubled to 2."""
    s = build(cards, ["Solphim, Mayhem Dominus", "Lightning Bolt"], ["Gisela, Blade of Goldnight"], forests=20)
    respond_on(s)
    put(s, "Solphim, Mayhem Dominus")
    put(s, "Gisela, Blade of Goldnight", "p2")
    bolt = all_bolts(s)["p1"][0]
    bolt_from(s, bolt, "p2")
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p2", (d.player, d.kind, d.prompt)  # (the damaged player orders them)
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[answer])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 40 - dealt, life(s, "p2")
    check(s)


def test_ulamog_countered_still_destroys_and_then_shuffles_the_graveyard_in(cards):
    """Ulamog, the Infinite Gyre: "When you cast this spell, destroy target permanent." is independent of the spell (113.7a, 603.3); "When
    Ulamog is put into a graveyard from anywhere, its owner shuffles their graveyard into their library." — a countered spell goes from the
    stack to the graveyard, and the shuffle takes the cards already there too."""
    s = build(cards, ["Ulamog, the Infinite Gyre", "Sol Ring"], ["Grizzly Bears", "Counterspell"], forests=20)
    respond_on(s)
    bears = put(s, "Grizzly Bears", "p2")
    ring = put(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[ring.id], to={"player": "p1", "zone": "graveyard"})
    ulamog = to_hand(s, "Ulamog, the Infinite Gyre")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, C=11)
    act(s, "p1", type="cast_spell", card_id=ulamog.id, targets=[bears.id])
    d = s.state.rules.decision
    if d is not None:  # (the trigger's target, if it is asked)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == bears.id)])
    mana(s, "p2", U=2)
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[ulamog.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[ulamog.id].zone == "p1:library" and ring.id in s.state.zones["p1:library"] and not s.state.zones["p1:graveyard"], (
        s.state.cards[ulamog.id].zone, names(s, "graveyard"))
    check(s)


@pytest.mark.parametrize(("division", "expected"), [([1, 1], (2, 2)), ([2, 0], (4, None))])
def test_earth_crystal_doubles_each_part_of_a_distribution(cards, division, expected):
    """The Earth Crystal: "{4}{G}{G}, {T}: Distribute two +1/+1 counters among one or two target creatures you control." and "If one or more
    +1/+1 counters would be put on a creature you control, twice that many … instead." (601.2d, 614.1) The two are divided first (1 and 1, or
    both on one creature), and each creature's share is doubled: 2 and 2, or 4 on one."""
    s = build(cards, ["The Earth Crystal", "Grizzly Bears", "Llanowar Elves"], forests=20)
    crystal, bears, elves = put(s, "The Earth Crystal"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, G=2, C=4)
    targets = [bears.id, elves.id] if division[1] else [bears.id]
    act(s, "p1", type="activate_ability", card_id=crystal.id, ability=2, targets=targets, target_counts=[len(targets)], division=division if division[1] else [])  # (one target gets both without a division)
    settle(s)
    got = (s.state.cards[bears.id].counters.get("+1/+1", 0), s.state.cards[elves.id].counters.get("+1/+1", 0) if division[1] else None)
    assert got == expected, got
    check(s)


def test_elas_il_kor_sees_the_others_die_with_it_and_drains_every_opponent(cards):
    """Elas il-Kor, Sadistic Pilgrim: "Whenever another creature you control dies, each opponent loses 1 life." A sweeper kills Elas and two
    other creatures at once: she sees them die (603.10a leaves-the-battlefield look-back), so each opponent loses 2 — not for herself, nor
    for Bob's creature — and with three players both opponents lose it."""
    s = three(cards, ["Elas il-Kor, Sadistic Pilgrim", "Grizzly Bears", "Llanowar Elves", "Day of Judgment"], ["Grizzly Bears"])
    put(s, "Elas il-Kor, Sadistic Pilgrim")
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Day of Judgment")
    mana(s, W=2, C=2)
    cast(s, "Day of Judgment")
    assert [c for c in names(s, "battlefield") if c != "Forest"] == []
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == (38, 38, 40), (life(s, "p2"), life(s, "p3"), life(s, "p1"))
    check(s)


def test_marionette_apprentice_counts_an_artifact_creature_once(cards):
    """Marionette Apprentice: "Whenever another creature or artifact you control is put into a graveyard from the battlefield, each opponent
    loses 1 life." A Servo (an artifact creature, 205.1b) is one object: one trigger, not two; Bob's artifact doesn't count."""
    s = build(cards, ["Marionette Apprentice", "Lightning Bolt"], ["Sol Ring"], forests=20)
    put(s, "Marionette Apprentice")
    servo = make_token(s, "p1", "Servo", "Token Artifact Creature — Servo", "1/1")
    ring = put(s, "Sol Ring", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[servo])
    assert life(s, "p2") == 39, life(s, "p2")
    act(s, "p2", type="move", card_ids=[ring.id], to={"player": "p2", "zone": "graveyard"})
    assert life(s, "p2") == 39
    check(s)


def test_zopandrel_doubles_the_current_power_and_toughness_at_every_combat(cards):
    """Zopandrel, Hunger Dominus: "At the beginning of each combat, double the power and toughness of each creature you control until end of
    turn." (701.10: +X/+X where X is each creature's own value as the effect resolves, Giant Growth's +3/+3 included, 613.4c.) Each combat —
    Bob's too — and each creature separately."""
    s = build(cards, ["Zopandrel, Hunger Dominus", "Grizzly Bears", "Giant Growth"], forests=20)
    respond_on(s)
    put(s, "Zopandrel, Hunger Dominus")
    bears = put(s, "Grizzly Bears")
    zbase = pt(s, "Zopandrel, Hunger Dominus")
    to_hand(s, "Giant Growth")
    mana(s, G=1)
    cast(s, "Giant Growth", targets=[bears.id])
    assert pt(s, "Grizzly Bears") == (5, 5)
    to_phase(s, "declare_attackers", turn=1)  # (the beginning-of-combat trigger has resolved by then)
    assert pt(s, "Grizzly Bears") == (10, 10) and pt(s, "Zopandrel, Hunger Dominus") == (zbase[0] * 2, zbase[1] * 2), (
        pt(s, "Grizzly Bears"), pt(s, "Zopandrel, Hunger Dominus"))
    check(s)


def test_sheoldred_makes_each_opponent_sacrifice_their_own_choice_in_their_own_upkeep(cards):
    """Sheoldred, Whispering One: "At the beginning of each opponent's upkeep, that player sacrifices a creature of their choice." With three
    players: Bob chooses in his upkeep and Carol in hers (701.21a: their creatures, their choice — never Alice's), and Alice's own upkeep
    trigger returns a creature card from her graveyard."""
    s = three(cards, ["Sheoldred, Whispering One", "Grizzly Bears"], ["Grizzly Bears", "Twisted Abomination"], ["Grizzly Bears", "Twisted Abomination"])
    respond_on(s)
    put(s, "Sheoldred, Whispering One")
    mine = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "graveyard"})
    for pid in ("p2", "p3"):
        put(s, "Grizzly Bears", pid)
        put(s, "Twisted Abomination", pid)
    asked = []
    for _ in range(150):
        if s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        d = s.state.rules.decision
        if d is not None:
            asked.append((s.state.turn.number, d.player, d.kind))
            if d.kind in ("declare_attackers", "declare_blockers"):
                act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
            else:
                pick = [o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Twisted Abomination"] or [o.id for o in d.options]
                act(s, d.player, type="choose", decision_id=d.id, option_ids=pick[:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert [(t, p) for t, p, k in asked if k == "choose_cards"] == [(2, "p2"), (3, "p3")], asked  # (each opponent picks, in their own turn)
    assert names(s, "battlefield", "p2").count("Grizzly Bears") == 1 and "Twisted Abomination" not in names(s, "battlefield", "p2"), names(s, "battlefield", "p2")
    assert names(s, "battlefield", "p3").count("Grizzly Bears") == 1 and "Twisted Abomination" not in names(s, "battlefield", "p3"), names(s, "battlefield", "p3")
    assert names(s, "battlefield").count("Grizzly Bears") == 1  # (Alice's own upkeep: the Bears from her graveyard)
    check(s)


@pytest.mark.parametrize("with_land", [True, False])
def test_gitrog_monster_upkeep_sacrifice_a_land_draws_or_it_is_sacrificed(cards, with_land):
    """The Gitrog Monster: "At the beginning of your upkeep, sacrifice The Gitrog Monster unless you sacrifice a land." and "Whenever one or
    more land cards are put into your graveyard from anywhere, draw a card." (118.12) The land sacrificed to keep it is a land card going to the
    graveyard, so it draws one more card than the draw step; with no land to sacrifice the Gitrog Monster itself is sacrificed."""
    s = build(cards, ["The Gitrog Monster"], forests=20)
    respond_on(s)
    gitrog = put(s, "The Gitrog Monster")
    if with_land:
        land = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "upkeep", turn=3)
    hand = len(s.state.zones["p1:hand"])
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None and s.state.turn.phase == "upkeep":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Forest"), d.options[0].id)])
        elif s.state.zones.get("stack") or s.state.turn.phase == "upkeep":
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    to_phase(s, "main1", turn=3)
    settle(s)
    if with_land:
        assert s.state.cards[gitrog.id].zone == "p1:battlefield" and land.id in s.state.zones["p1:graveyard"]
        assert len(s.state.zones["p1:hand"]) == hand + 2, (hand, len(s.state.zones["p1:hand"]))  # draw step + the Gitrog Monster
    else:
        assert s.state.cards[gitrog.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_grenzo_only_offers_the_goad_mode_when_that_player_has_a_creature_and_any_color_covers_one_card(cards):
    """Grenzo, Havoc Raiser: "choose one — Goad target creature that player controls; or exile the top card of that player's library. Until
    end of turn, you may cast that card and you may spend mana as though it were mana of any color to cast that spell." Bob has no creature, so
    the first mode has no legal target and can't be chosen (601.2b, 700.2a); the exiled Bolt may be paid with green mana (609.4b), and
    only that spell is."""
    s = build(cards, ["Grenzo, Havoc Raiser", "Lightning Bolt"], ["Lightning Bolt"], forests=20)
    grenzo = put(s, "Grenzo, Havoc Raiser")
    to_phase(s, "declare_attackers", turn=3)
    theirs = card_named(s, "Lightning Bolt", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "library"}, position="top")
    to_hand(s, "Lightning Bolt")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": grenzo.id, "target": "p2"}])
    modes_seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == "main2":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            modes_seen.append([o.label for o in d.options])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[-1].id])
    settle(s)
    assert not any("Goad" in label for labels in modes_seen for label in labels), modes_seen
    assert s.state.cards[theirs.id].zone == "p2:exile", s.state.cards[theirs.id].zone
    mana(s, G=1)
    mine = card_named(s, "Lightning Bolt")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])  # (Alice's own Bolt still needs red)
    act(s, "p1", type="cast_spell", card_id=theirs.id, targets=["p2"])
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and life(s, "p2") == 40 - 2 - 3, (s.state.cards[theirs.id].zone, life(s, "p2"))
    check(s)


def test_thassa_deep_dwelling_flickers_under_your_control_not_the_owners(cards):
    """Thassa, Deep-Dwelling: "At the beginning of your end step, exile up to one other target creature you control, then return that card to
    the battlefield under your control." — unlike Displacer Kitten it says "your control": Bob's Bears that Alice controls come back to Alice
    (the owner is still Bob, 110.2), as a new untapped object (400.7); a token doesn't come back at all (111.7)."""
    s = build(cards, ["Thassa, Deep-Dwelling"], ["Grizzly Bears"], forests=20)
    respond_on(s)
    put(s, "Thassa, Deep-Dwelling")
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    act(s, "p1", type="tap", card_ids=[bears.id], tapped=True)  # (the flicker brings it back untapped: a new object)
    to_phase(s, "end", turn=1)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options if o.card_id == bears.id] or [d.options[0].id]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    got = s.state.cards[bears.id]
    assert (got.zone, got.owner, got.controller, got.tapped) == ("p1:battlefield", "p2", "p1", False), (got.zone, got.owner, got.controller, got.tapped)
    check(s)


@pytest.mark.parametrize(("when", "back_on_turn"), [("main1", 1), ("end", 2)])
def test_nezahal_returns_at_the_next_end_step_not_the_one_already_begun(cards, when, back_on_turn):
    """Nezahal, Primal Tide: "Discard three cards: Exile Nezahal. Return it to the battlefield tapped under its owner's control at the beginning
    of the next end step." (603.7: a delayed trigger waits for the next time the step begins — activated in the end step itself it
    waits for the following turn's.) It comes back as a new object, tapped."""
    s = build(cards, ["Nezahal, Primal Tide"], forests=20)
    respond_on(s)
    nez = put(s, "Nezahal, Primal Tide")
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:4]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, when, turn=1)
    act(s, "p1", type="activate_ability", card_id=nez.id, ability=3)
    for _ in range(4):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices) if d.min_choices else 3])
    if s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
        while s.state.zones.get("stack") and s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[nez.id].zone == "p1:exile" and len(s.state.zones["p1:hand"]) == hand - 3, (s.state.cards[nez.id].zone, len(s.state.zones["p1:hand"]))
    seen_back = None
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            if s.state.cards[nez.id].zone == "p1:battlefield":
                seen_back = s.state.turn.number
                break
            if s.state.turn.number == 3:
                break
            act(s, s.state.rules.priority, type="pass_priority")
    assert seen_back == back_on_turn, seen_back
    assert s.state.cards[nez.id].tapped and s.state.cards[nez.id].controller == "p1"
    check(s)


def test_annihilator_hits_the_controller_of_the_attacked_planeswalker_not_the_first_opponent(cards):
    """Ulamog, the Infinite Gyre: "Annihilator 4 (Whenever this creature attacks, defending player sacrifices four permanents of their
    choice.)" Attacking Carol's planeswalker makes Carol the defending player (506.3d, 702.86a): she sacrifices, and Bob doesn't."""
    s = three(cards, ["Ulamog, the Infinite Gyre"], ["Island"], ["Jace Beleren", "Island"])
    ulamog = put(s, "Ulamog, the Infinite Gyre")
    jace = put(s, "Jace Beleren", "p3")
    act(s, "p3", type="counter", card_ids=[jace.id], kind="loyalty", delta=3)
    for pid in ("p2", "p3"):
        for c in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == pid and c.zone == f"{pid}:library"][:6]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    before = {pid: len(s.state.zones[f"{pid}:battlefield"]) for pid in ("p2", "p3")}
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ulamog.id, "target": jace.id}])
    asked = []
    for _ in range(14):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        asked.append((d.player, d.kind))
        if d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert [p for p, k in asked if k == "choose_cards"] == ["p3"], asked  # (Bob only gets to declare no blockers)
    assert len(s.state.zones["p2:battlefield"]) == before["p2"]
    assert len(s.state.zones["p3:battlefield"]) <= before["p3"] - 4, (before, len(s.state.zones["p3:battlefield"]))
    check(s)


FULL_AFTER_FALSIFICATION = [
    "Displacer Kitten", "Helm of the Host", "Mondrak, Glory Dominus", "Elspeth, Storm Slayer", "Ephemerate", "Whip of Erebos",
    "Wishclaw Talisman", "Malakir Rebirth // Malakir Mire", "Enduring Vitality", "Sundering Eruption // Volcanic Fissure",
    "Vorinclex, Monstrous Raider", "Ozolith, the Shattered Spire", "The Earth Crystal", "Delayed Blast Fireball", "Lathril, Blade of the Elves",
    "Alchemist's Talent", "Ragavan, Nimble Pilferer", "Professional Face-Breaker", "Lotho, Corrupt Shirriff", "Crypt Ghast", "Scute Swarm",
    "Plaguebearer", "Greater Good", "Nasty End", "Dina, Soul Steeper", "Phyrexian Metamorph", "Anim Pakal, Thousandth Moon",
    "Gisela, Blade of Goldnight", "Solphim, Mayhem Dominus", "Ulamog, the Infinite Gyre", "Elas il-Kor, Sadistic Pilgrim", "Marionette Apprentice",
    "Zopandrel, Hunger Dominus", "Sheoldred, Whispering One", "The Gitrog Monster", "Grenzo, Havoc Raiser", "Thassa, Deep-Dwelling",
    "Nezahal, Primal Tide", "Tireless Tracker",
]


@pytest.mark.parametrize("name", FULL_AFTER_FALSIFICATION)
def test_falsified_cards_are_still_full(cards, name):
    """Every card above survived its adversarial scenario (or was fixed) and stays FULL: the scenarios are the proof."""
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
