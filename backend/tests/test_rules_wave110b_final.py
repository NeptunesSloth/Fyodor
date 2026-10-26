"""Wave 110B final pass (real Oracle text in tests/fixtures/wave110b_cards.json).

* Clandestine Chameleon: 613.1f / 123.2 it has the abilities of ability stickers on other permanents its owner owns and on cards in its owner's graveyard, and no others.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.game.errors import ActionError
from app.game.state import StickerDefinition101, StickerPlacement101
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import (
    attack,
    build,
    card_named,
    cast,
    ch,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    settle,
    top,
)


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Clandestine Chameleon", "Ichor Elixir"])  # Ichor Elixir: 901.3, 901.9 planar dice are Planechase-only; none is rolled in Commander
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def at(s, name, zone, pid):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return c


def stick(s, c, text="Flying"):
    s.state.cards[c.id].stickers101.append(StickerPlacement101(sticker=StickerDefinition101(id=f"t{c.id}", kind="ability", cost=1, label=text, text=text), owner="p1"))


@pytest.mark.parametrize("zone,owner,flies", [("battlefield", "p1", True), ("graveyard", "p1", True), ("hand", "p1", False), ("battlefield", "p2", False)])
def test_chameleon_gets_sticker_abilities(cards, zone, owner, flies):
    s = build(cards, ["Clandestine Chameleon", "Grizzly Bears"], ["Grizzly Bears"])
    cham = put(s, "Clandestine Chameleon")
    bears = at(s, "Grizzly Bears", zone, owner)
    assert "flying" not in ch(s, cham).keywords
    stick(s, bears)
    assert ("flying" in ch(s, cham).keywords) is flies


def test_chameleon_ignores_its_own_and_others_unaffected(cards):
    s = build(cards, ["Clandestine Chameleon", "Grizzly Bears"])
    cham, bears = put(s, "Clandestine Chameleon"), put(s, "Grizzly Bears")
    stick(s, bears)
    assert "flying" in ch(s, cham).keywords and "flying" in ch(s, bears).keywords
    assert card_named(s, "Grizzly Bears").stickers101  # the Bears keep their sticker; the Chameleon only copies the ability
    assert not s.state.cards[cham.id].stickers101


BRINK = "Back from the Brink"


@pytest.mark.parametrize("name", [BRINK, "Braided Net // Braided Quipu", "Lukka, Coppercoat Outcast", "Throne of the Grim Captain // The Grim Captain", "Soundwave, Sonic Spy // Soundwave, Superior Captain"])
def test_brink_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def to_gy(s, name, pid="p1"):
    return at(s, name, "graveyard", pid)


def brink_ability(s, c):
    return next((a.index for a in ch(s, c).abilities if "Exile this card from your graveyard" in a.text and "token" in a.text), None)


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == "p1:battlefield"]


def activate(s, c):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=brink_ability(s, c))
    settle(s)


def test_brink_exile_and_pay_mana_cost_makes_a_token_copy(cards):
    """602.2b the exile is part of the cost; 118.1 the mana cost is paid (not cast); 707.2 a token copy that has the card's characteristics; opponents' graveyards are not used."""
    s = build(cards, ["Back from the Brink", "Hill Giant", "Endless One"], ["Hill Giant"])
    put(s, BRINK)
    to_gy(s, "Endless One")
    giant, theirs = to_gy(s, "Hill Giant"), to_gy(s, "Hill Giant", "p2")
    settle(s)
    assert brink_ability(s, theirs) is None and brink_ability(s, giant) is not None
    mana(s, R=1, C=3)
    activate(s, giant)
    assert s.state.cards[giant.id].zone == "p1:exile"
    assert len(tokens(s, "Hill Giant")) == 1 and "Creature" in ch(s, tokens(s, "Hill Giant")[0]).types
    assert not s.state.players["p1"].mana or sum(s.state.players["p1"].mana.values()) == 0
    check(s)


def test_brink_x_in_mana_cost_is_zero_and_needs_the_mana(cards):
    """Ruling 2011-09-22: X is 0 in the cost paid (Endless One costs {0}); without the mana the activation is refused."""
    s = build(cards, ["Back from the Brink", "Hill Giant", "Endless One"], [])
    put(s, BRINK)
    giant, one = to_gy(s, "Hill Giant"), to_gy(s, "Endless One")
    settle(s)
    with pytest.raises(ActionError):
        activate(s, giant)  # (no mana)
    assert s.state.cards[giant.id].zone == "p1:graveyard"
    activate(s, one)
    assert s.state.cards[one.id].zone == "p1:exile" and not tokens(s, "Endless One")  # (the 0/0 token copy dies at once: X is 0 for the copy too)
    assert any("token" in "".join(x.t or "" for x in e.parts).lower() for e in s.state.log[-8:])
    check(s)


def test_brink_double_faced_card_pays_front_face_cost_and_copies_front_face(cards):
    """Ruling 2011-09-22: a double-faced creature card exiled this way costs its front face's mana cost and the token is a copy of the front face."""
    s = build(cards, ["Back from the Brink", "Delver of Secrets // Insectile Aberration"], [])
    put(s, BRINK)
    delver = to_gy(s, "Delver of Secrets // Insectile Aberration")
    settle(s)
    assert brink_ability(s, delver) is not None
    mana(s, U=1)
    activate(s, delver)
    assert s.state.cards[delver.id].zone == "p1:exile" and len(tokens(s, "Delver of Secrets")) == 1
    check(s)


NET = "Braided Net // Braided Quipu"


def find_ab(s, c, contains):
    return next(a.index for a in ch(s, c).abilities if contains in a.text)


def test_braided_net_locks_activated_abilities_while_tapped(cards):
    """611.2b, 602.5: the target is tapped and its activated abilities can't be activated for as long as it remains tapped; once it untaps they can again (400.7 it is that object)."""
    s = build(cards, [NET, "Shivan Dragon"], [])
    mana(s, U=1, C=2)
    cast(s, NET)  # (enters with three net counters)
    net, dragon = card_named(s, NET), put(s, "Shivan Dragon")
    settle(s)
    assert s.state.cards[net.id].counters.get("net") == 3
    mana(s, R=2)
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=find_ab(s, dragon, "+1/+0"))  # (before the lock)
    settle(s)
    act(s, "p1", type="activate_ability", card_id=net.id, ability=find_ab(s, net, "Remove a net counter"), targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].tapped and s.state.cards[net.id].counters.get("net") == 2
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=dragon.id, ability=find_ab(s, dragon, "+1/+0"))
    check(s)
    act(s, "p1", type="tap", card_ids=[dragon.id])
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=find_ab(s, dragon, "+1/+0"))  # (untapped: the lock is over)
    settle(s)
    check(s)


def test_braided_net_can_target_an_already_tapped_permanent(cards):
    """Ruling 2023-11-10: an already tapped permanent is a legal target; its abilities are locked for as long as it stays tapped."""
    s = build(cards, [NET, "Shivan Dragon"], [])
    mana(s, U=1, C=2)
    cast(s, NET)  # (enters with three net counters)
    net, dragon = card_named(s, NET), put(s, "Shivan Dragon")
    act(s, "p1", type="tap", card_ids=[dragon.id])
    settle(s)
    act(s, "p1", type="activate_ability", card_id=net.id, ability=find_ab(s, net, "Remove a net counter"), targets=[dragon.id])
    settle(s)
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=dragon.id, ability=find_ab(s, dragon, "+1/+0"))


LUKKA = "Lukka, Coppercoat Outcast"


def lukka_on(s, loyalty=5):
    lk = put(s, LUKKA)
    act(s, "p1", type="counter", card_ids=[lk.id], kind="loyalty", delta=loyalty - s.state.cards[lk.id].counters.get("loyalty", 0))
    return lk


def test_lukka_plus_exiled_creatures_castable_while_a_lukka_planeswalker_is_controlled(cards):
    """611.2b, 113.6m: creature cards exiled by +1 may be cast from exile for as long as you control a Lukka planeswalker; other cards exiled with them may not; losing the
    planeswalker ends it (2020-04-17: any Lukka planeswalker, not just the one that exiled the card)."""
    s = build(cards, [LUKKA, "Grizzly Bears", "Lightning Bolt", "Hill Giant"], [])
    for n in ("Hill Giant", "Lightning Bolt", "Grizzly Bears"):
        top(s, n)
    lk = lukka_on(s)
    act(s, "p1", type="activate_ability", card_id=lk.id, ability=find_ab(s, lk, "Exile the top three"))
    settle(s)
    bears, bolt, giant = (card_named(s, n) for n in ("Grizzly Bears", "Lightning Bolt", "Hill Giant"))
    assert {s.state.cards[c.id].zone for c in (bears, bolt, giant)} == {"p1:exile"}
    mana(s, G=1, R=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # (not a creature card)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    act(s, "p1", type="move", card_ids=[lk.id], to={"player": "p1", "zone": "graveyard"})  # (no Lukka planeswalker any more)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=giant.id)
    check(s)


@pytest.mark.parametrize("gone,expect", [("Grizzly Bears", "Hill Giant"), ("Serra Angel", "Shivan Dragon")])
def test_lukka_minus_reveals_until_greater_mana_value(cards, gone, expect):
    """608.2h, 701.20: the exiled creature's mana value (as it last existed) is the bar: the first revealed creature card above it enters, the rest go to the bottom."""
    s = build(cards, [LUKKA, "Grizzly Bears", "Serra Angel", "Hill Giant", "Shivan Dragon"], [])
    for n in ("Shivan Dragon", "Hill Giant"):
        top(s, n)
    lk = lukka_on(s)
    victim = put(s, gone)
    act(s, "p1", type="activate_ability", card_id=lk.id, ability=find_ab(s, lk, "Exile target creature"), targets=[victim.id])
    drive(s)
    assert s.state.cards[victim.id].zone == "p1:exile"
    assert s.state.cards[card_named(s, expect).id].zone == "p1:battlefield"
    other = "Shivan Dragon" if expect == "Hill Giant" else "Hill Giant"
    assert s.state.cards[card_named(s, other).id].zone == "p1:library"  # (not revealed, or revealed but too small: bottom of the library)
    if expect == "Shivan Dragon":
        assert s.state.zones["p1:library"].index(card_named(s, "Hill Giant").id) >= len(s.state.zones["p1:library"]) - 2
    check(s)


THRONE = "Throne of the Grim Captain // The Grim Captain"
MATERIALS = ("Orazca Frillback", "Merfolk of the Pearl Trident", "Swab Goblin", "Vampire Noble")


def crafted(cards):
    """Alice crafts the Throne: the Dinosaur and Merfolk from the battlefield, the Pirate and Vampire from the graveyard."""
    s = build(cards, [THRONE, *MATERIALS, "Grizzly Bears"], ["Grizzly Bears", "Hill Giant"])
    throne = put(s, THRONE)
    dino, fish = put(s, MATERIALS[0]), put(s, MATERIALS[1])
    pirate, vamp = at(s, MATERIALS[2], "graveyard", "p1"), at(s, MATERIALS[3], "graveyard", "p1")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=throne.id, ability=1)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    settle(s)
    return s, throne, (dino, fish, pirate, vamp)


@pytest.mark.parametrize("pick", [0, 3, None])
def test_grim_captain_attack_trigger(cards, pick):
    """702.167c, 508.4, 701.21: each opponent sacrifices a nonland permanent; then you may put one exiled creature card used to craft it onto the battlefield tapped and
    attacking (not declared as an attacker; none if you decline)."""
    s, throne, mats = crafted(cards)
    assert s.state.cards[throne.id].face == 1 and all(s.state.cards[c.id].zone == "p1:exile" for c in mats)
    bears = put(s, "Grizzly Bears", "p2")
    attack(s, s.state.cards[throne.id])
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            break
        crafted_q = "used to craft" in d.prompt
        ids = ([mats[pick].id] if pick is not None else []) if crafted_q else [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    entered = [i for i, c in enumerate(mats) if s.state.cards[c.id].zone == "p1:battlefield"]
    assert entered == ([] if pick is None else [pick])
    power = 0 if pick is None else int(ch(s, mats[pick]).pt[0])
    assert life(s, "p2") == 40 - 7 - power and (pick is None or s.state.cards[mats[pick].id].tapped)  # (it attacked: its damage was dealt; the Captain's 7 unblocked)
    check(s)


SOUND = "Soundwave, Sonic Spy // Soundwave, Superior Captain"


def soundwave_hit(cards, power, *, cast=True):
    """Alice's Goblin token (the given power) hits Bob, whose graveyard holds Lightning Bolt (mana value 1) and Divination (3); returns the table and the prompts asked."""
    from tests.wave110b_kit import token_of

    s = build(cards, [SOUND, "Grizzly Bears"], ["Lightning Bolt", "Divination", "Lightning Helix"])
    wave = put(s, SOUND)
    for n in ("Lightning Bolt", "Divination", "Lightning Helix"):
        at(s, n, "graveyard", "p2")
    tok = token_of(s, "p1", "Goblin", "Creature — Goblin", f"{power}/{power}")
    asked: list[Any] = []

    def answer(d):
        asked.append((d.kind, d.prompt))
        if "(or none)" in d.prompt:
            return [d.options[0].id] if cast else []
        return None

    attack(s, tok)
    for _ in range(60):
        d = s.state.rules.decision
        if d is None and s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            ids = answer(d)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids if ids is not None else [o.id for o in d.options][: max(1, d.min_choices)])
    return s, wave, asked


@pytest.mark.parametrize("power,exiled,token", [(3, "Divination", "Ravage"), (1, "Lightning Bolt", "Ravage"), (2, "Lightning Helix", "Laserbeak")])
def test_soundwave_exiles_the_card_with_mana_value_equal_to_the_damage_and_converts(cards, power, exiled, token):
    """603.2c, 701.28: the batch's damage is the mana value asked for; the card is exiled, copied and cast free; casting it converts Soundwave, whose back face then triggers
    on that very cast (odd: Ravage, even: Laserbeak) and converts it back."""
    s, wave, _ = soundwave_hit(cards, power)
    others = {"Divination", "Lightning Bolt", "Lightning Helix"} - {exiled}
    assert s.state.cards[card_named(s, exiled, "p2").id].zone == "p2:exile"
    assert all(s.state.cards[card_named(s, n, "p2").id].zone == "p2:graveyard" for n in others)
    assert any(c.is_token and c.name == token for c in s.state.cards.values())
    assert s.state.cards[wave.id].face == 0  # (converted by the ability, then back by the odd/even trigger)
    check(s)


def test_soundwave_declined_cast_does_not_convert(cards):
    """If you do: no cast, no conversion (the card stays exiled)."""
    s, wave, _ = soundwave_hit(cards, 3, cast=False)
    assert s.state.cards[card_named(s, "Divination", "p2").id].zone == "p2:exile" and s.state.cards[wave.id].face == 0
    assert not any(c.is_token and c.name in ("Ravage", "Laserbeak") for c in s.state.cards.values())
    check(s)
