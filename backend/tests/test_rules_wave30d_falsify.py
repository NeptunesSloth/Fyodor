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
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_multitarget import respond_on
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

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
