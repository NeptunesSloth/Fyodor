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
    to_hand,
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


@pytest.mark.parametrize("name", [BRINK, "Braided Net // Braided Quipu", "Lukka, Coppercoat Outcast", "Throne of the Grim Captain // The Grim Captain", "Soundwave, Sonic Spy // Soundwave, Superior Captain", "Thief of Blood", "Torrent of Lava", "River Song", "Sanar, Innovative First-Year", "The Dragon-Kami Reborn // Dragon-Kami's Egg"])
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


THIEF = "Thief of Blood"


def test_thief_of_blood_removes_every_counter_and_enters_with_that_many(cards):
    """614.12, 122.6, 122.1: every counter on every permanent (loyalty included, an opponent's too) comes off as it enters; it enters with a +1/+1 counter for each."""
    s = build(cards, [THIEF, "Grizzly Bears", LUKKA], ["Grizzly Bears"])
    mine, theirs, lk = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, LUKKA)
    act(s, "p1", type="set_counter", card_id=mine.id, kind="+1/+1", value=2)
    act(s, "p1", type="set_counter", card_id=mine.id, kind="stun", value=1)
    act(s, "p1", type="set_counter", card_id=theirs.id, kind="-1/-1", value=1)
    act(s, "p1", type="set_counter", card_id=lk.id, kind="loyalty", value=5)
    mana(s, B=2, C=4)
    cast(s, THIEF)
    thief = card_named(s, THIEF)
    assert all(not s.state.cards[c.id].counters for c in (mine, theirs, lk))
    assert s.state.cards[thief.id].counters == {"+1/+1": 9}
    from app.rules import sba
    assert sba.power(s.state.cards[thief.id], ch(s, thief)) == 10
    check(s)


def test_thief_of_blood_with_no_counters_enters_plain(cards):
    s = build(cards, [THIEF], [])
    mana(s, B=2, C=4)
    cast(s, THIEF)
    assert not s.state.cards[card_named(s, THIEF).id].counters
    check(s)


TORRENT = "Torrent of Lava"


def test_torrent_of_lava_grants_the_shield_ability_only_while_on_the_stack(cards):
    """113.6, 611.3a: while Torrent of Lava is on the stack each creature has "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn"
    (Alice uses it on her Bears while holding priority); the damage is X to each creature without flying; the shielded creature takes 1 less; the ability is gone once it has
    resolved."""
    s = build(cards, [TORRENT, "Grizzly Bears", "Hill Giant", "Serra Angel"], [])
    act(s, "p1", type="set_prefs", hold_priority=True)  # (so the spell stays on the stack and Alice may act)
    bears, giant, angel = put(s, "Grizzly Bears"), put(s, "Hill Giant"), put(s, "Serra Angel")
    for c in (bears, giant, angel):
        s.state.rules.controlled_since[c.id].turn = 0
    assert not any("Torrent" in a.text for a in ch(s, bears).abilities)
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, TORRENT).id, x_value=2)
    assert any("Torrent of Lava this turn" in a.text for a in ch(s, bears).abilities) and s.state.zones["stack"]
    act(s, "p1", type="activate_ability", card_id=bears.id, ability=find_ab(s, bears, "Prevent the next 1 damage"))
    settle(s)
    assert s.state.cards[bears.id].tapped
    assert s.state.cards[bears.id].damage == 1 and s.state.cards[giant.id].damage == 2 and s.state.cards[angel.id].damage == 0  # (2 each, 1 prevented for the Bears; the Angel flies)
    assert not any("Torrent" in a.text for a in ch(s, bears).abilities)
    check(s)


RIVER = "River Song"


def test_river_song_draws_from_the_bottom_while_it_is_on_the_battlefield(cards):
    """121.1, 614.1 (ruling 2023-10-13): every card its controller draws comes from the bottom of their library, the bottom card first; without River Song from the top."""
    s = build(cards, [RIVER, "Divination", "Grizzly Bears", "Hill Giant"], [])
    for n in ("Hill Giant", "Grizzly Bears"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"zone": "library"}, position="bottom")
    to_hand(s, "Divination")
    lib = list(s.state.zones["p1:library"])
    mana(s, U=1, C=2)
    cast(s, "Divination")  # (no River Song yet: the top two)
    assert set(lib[:2]) <= set(s.state.zones["p1:hand"]) and not {lib[-1], lib[-2]} & set(s.state.zones["p1:hand"])
    put(s, RIVER)
    act(s, "p1", type="move", card_ids=[card_named(s, "Divination").id], to={"zone": "hand"})
    mana(s, U=1, C=2)
    cast(s, "Divination")
    assert {lib[-1], lib[-2]} <= set(s.state.zones["p1:hand"])  # (the two bottom cards, Bears and Giant)
    check(s)


@pytest.mark.parametrize("spell,extra", [("Opt", {}), ("Consider", {}), ("Rampant Growth", {})])
def test_river_song_spoilers_counter_and_damage_when_an_opponent_scries_surveils_or_searches(cards, spell, extra):
    """603.2, 701.22, 701.25, 701.23: Bob's scry / surveil / own-library search puts a +1/+1 counter on River Song, then it deals damage equal to its power (2+1) to Bob."""
    from tests.wave100c_kit import to_phase

    s = build(cards, [RIVER], [spell, "Forest", "Island"], forests=3, islands=3)
    put(s, RIVER)
    to_phase(s, "main1", 2)
    mana(s, "p2", U=1, G=1, C=1)
    cast_p2 = to_hand(s, spell, "p2")
    act(s, "p2", type="cast_spell", card_id=cast_p2.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    song = card_named(s, RIVER)
    assert s.state.cards[song.id].counters.get("+1/+1") == 1 and life(s, "p2") == 40 - 3
    check(s)


SANAR = "Sanar, Innovative First-Year"


def test_sanar_vivid_exiles_one_revealed_card_per_color_and_lets_them_be_cast(cards):
    """701.20, 608.2d, 614.12: reveal until X nonland cards (X = colors among your permanents: Sanar's two and the Bears' green = 3); for each of those colors you may exile
    one revealed card of that color; then shuffle; the exiled cards may be cast this turn (Bolt is red, Divination blue, no green card was revealed)."""

    s = build(cards, [SANAR, "Grizzly Bears", "Lightning Bolt", "Hill Giant", "Divination"], [])
    put(s, SANAR)
    put(s, "Grizzly Bears")
    for n in ("Divination", "Hill Giant", "Lightning Bolt"):
        top(s, n)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:2]
    for f in forests:  # (the first is drawn for the turn, the second is revealed and not a nonland card)
        act(s, "p1", type="move", card_ids=[f.id], to={"zone": "library"}, position="top")
    asked: list[str] = []

    def pick(d):
        asked.append(d.prompt)
        names = {o.id: s.state.cards[o.card_id].name for o in d.options}
        want = {"blue": "Divination", "red": "Lightning Bolt"}.get(next((w for w in ("white", "blue", "black", "red", "green") if f"exile a {w} card" in d.prompt), ""), "")
        return [i for i, n in names.items() if n == want][:1] if want else []

    for _ in range(80):
        d = s.state.rules.decision
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif "Vivid" in d.prompt:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d))
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert [w for a in asked for w in ("blue", "red", "green") if f"exile a {w} card" in a] == ["blue", "red", "green"]  # (white and black are not among the permanents' colors)
    bolt, div = card_named(s, "Lightning Bolt"), card_named(s, "Divination")
    assert s.state.cards[bolt.id].zone == "p1:exile" and s.state.cards[div.id].zone == "p1:exile" and s.state.cards[card_named(s, "Hill Giant").id].zone == "p1:library"
    mana(s, U=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=div.id)
    settle(s)
    assert life(s, "p2") == 37 and s.state.cards[div.id].zone == "p1:graveyard"
    check(s)


KAMI = "The Dragon-Kami Reborn // Dragon-Kami's Egg"


def test_dragon_kami_chapter_one_exiles_a_card_face_down_with_a_hatching_counter(cards):
    """714.2, 122.1, 701.20: chapter I gains 2 life, looks at the top three cards, exiles one face down with a hatching counter and puts the rest on the bottom."""
    s = build(cards, [KAMI, "Grizzly Bears", "Hill Giant", "Lightning Bolt"], [])
    for n in ("Lightning Bolt", "Hill Giant", "Grizzly Bears"):
        top(s, n)
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, KAMI).id)

    def answer(d):
        if d.kind == "choose_cards" and d.min_choices == 1:
            return [o.id for o in d.options if s.state.cards[o.card_id].name == "Hill Giant"][:1]
        return None

    drive(s, answer)
    giant = card_named(s, "Hill Giant")
    assert life(s) == 42 and s.state.cards[giant.id].zone == "p1:exile" and s.state.cards[giant.id].counters == {"hatching": 1} and s.state.cards[giant.id].face_down
    lib = s.state.zones["p1:library"]
    assert {card_named(s, "Grizzly Bears").id, card_named(s, "Lightning Bolt").id} == set(lib[-2:])
    check(s)


@pytest.mark.parametrize("dies,casts", [("Egg", True), ("Dragon Whelp", True), ("Grizzly Bears", False)])
def test_dragon_kamis_egg_casts_a_hatching_creature_when_it_or_a_dragon_dies(cards, dies, casts):
    """603.10a, 118.9a: the Egg's own death or a Dragon's lets you cast a creature spell from among your exiled cards with hatching counters free; no other death does."""
    s = build(cards, [KAMI, "Hill Giant", "Goblin Chieftain", "Dragon Whelp", "Grizzly Bears", "Lightning Bolt"], [])
    egg = put(s, KAMI)
    act(s, "p1", type="set_face", card_id=egg.id, face=1)
    victims = {"Egg": egg, "Dragon Whelp": put(s, "Dragon Whelp"), "Grizzly Bears": put(s, "Grizzly Bears")}
    giant, chief = card_named(s, "Hill Giant"), card_named(s, "Goblin Chieftain")
    for c in (giant, chief):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="set_counter", card_id=giant.id, kind="hatching", value=1)  # (the Chieftain has none: not castable this way)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[victims[dies].id])
    seen: list[str] = []

    def answer(d):
        seen.append(d.prompt)
        return None

    drive(s, answer)
    assert s.state.cards[victims[dies].id].zone == "p1:graveyard"
    assert (s.state.cards[giant.id].zone == "p1:battlefield") is casts and s.state.cards[chief.id].zone == "p1:exile"
    check(s)
