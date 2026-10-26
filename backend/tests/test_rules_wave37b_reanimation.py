"""Wave 37B: reanimation and zone-destination wordings that stopped at one detail (CR 2026-09-25), real Oracle text
(tests/fixtures/wave37b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2c / 603.6a: "Return this card and target land card from your graveyard to the battlefield tapped." (Sandman, Slimefoot and Squee) is one
  instruction: both enter together, and only from the graveyard (113.6m). "… to the battlefield transformed" (Garland, 712.14a).
* 400.7: a card returned from a graveyard is a new object. ("The top creature card of your graveyard" — Shallow Grave, Corpse Dance, Mistmoon
  Griffin — is read since: tests/test_rules_wave110d_grave.py, tests/test_rules_wave40c_graveyard_order.py, tests/test_rules_wave110e_s8.py.)
* 614.1a, 616.1, 108.2a, 111.1: "If a card would be put into your graveyard from anywhere this turn, exile that card instead." (Yawgmoth's Will, Gaea's
  Will, Magus of the Will, Walk-In Closet) applies to a card from any zone, the resolving spell included, not to a token; a commander exiled this way may go
  to the command zone (903.9a).
* "from your hand or graveyard" (Danitha, Dread Tiller, Dakkon, Swift Warkite): the hand is hidden, so the choice is asked whenever the hand holds cards,
  whether or not one matches, and only the player choosing sees it.
* 608.2c: Remand puts the countered spell into its owner's hand; Betor's "mana value less than or equal to the amount of life you lost this turn"; Xu-Ifit's
  "It's a Skeleton in addition to its other types and has no abilities"; "that player" after a card from an opponent's graveyard (Geth, Nurgle's Conscription).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until, until_asked
from tests.wave9c_kit import build, card_named, cast, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave37b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w37b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA if c["name"] not in ("Thought Scour", "Mind Rot")]  # (those two are only the means of milling and discarding)


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def grave(s, name, pid="p1"):
    """Put this card into its owner's graveyard (the table's own move)."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def ability(s, name, pid="p1", contains=""):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])
    return next(a.index for a in ch.abilities if a.kind in ("activated", "mana", "loyalty") and contains in a.text)


def activate(s, pid, c, contains="", **kw):
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability(s, c.name, c.owner, contains), **kw)


def ask(s, limit=80):
    """Pass priority (declaring no attackers) until a decision is asked, and return it."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_attackers":
            return d
        if d is not None:
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("nothing was asked")


def names(s, zone, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{zone}", [])]


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_these_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def oid(s, c):
    return Plan(s.state, "p1", s.cards, None).oid(c.id)


# -- Sandman: "this card and target land card" (113.6m, 608.2c, 400.7) ------------------------------------------
def sandman_table(cards):
    s = build(cards, ["Sandman, Shifting Scoundrel"], forests=12)
    sandman = grave(s, "Sandman, Shifting Scoundrel")
    forest = grave(s, "Forest")
    return s, sandman, forest


def test_sandman_returns_itself_and_the_target_land_together_tapped(cards):
    """Both enter in one move, tapped, as new objects (400.7); the activation is from the graveyard."""
    s, sandman, forest = sandman_table(cards)
    before = (oid(s, sandman), oid(s, forest))
    mana(s, G=5)
    activate(s, "p1", sandman, targets=[forest.id])
    settle(s)
    assert zone_of(s, "Sandman, Shifting Scoundrel") == "p1:battlefield" and s.state.cards[forest.id].zone == "p1:battlefield"
    assert s.state.cards[sandman.id].tapped and s.state.cards[forest.id].tapped
    assert (oid(s, sandman), oid(s, forest)) != before  # 400.7: neither is the object that was in the graveyard
    check(s)


def test_sandman_does_not_work_from_the_battlefield(cards):
    """113.6m: an ability that returns this card from the graveyard works only there; a land alone is not returned by it."""
    s, sandman, forest = sandman_table(cards)
    put(s, "Sandman, Shifting Scoundrel")
    mana(s, G=5)
    with pytest.raises(ActionError):
        activate(s, "p1", sandman, targets=[forest.id])
    assert s.state.cards[forest.id].zone == "p1:graveyard"
    check(s)


# -- Garland: "to the battlefield transformed" (712.14a) ------------------------------------------------------------
def test_garland_returns_from_the_graveyard_with_its_back_face_up(cards):
    s = build(cards, ["Garland, Knight of Cornelia // Chaos, the Endless"], forests=12)
    garland = grave(s, "Garland, Knight of Cornelia // Chaos, the Endless")
    mana(s, B=2, R=2, G=3)
    before = oid(s, garland)
    activate(s, "p1", garland)
    settle(s)
    back = s.state.cards[garland.id]
    assert back.zone == "p1:battlefield" and back.face == 1  # 712.14a: it entered transformed
    assert Plan(s.state, "p1", s.cards, None).ch(back).name == "Chaos, the Endless"
    assert oid(s, garland) != before
    check(s)


# -- Yawgmoth's Will: every card going to your graveyard this turn is exiled (614.1a) -------------------------------------
def will_table(cards, *, mine=(), theirs=()):
    s = build(cards, ["Yawgmoth's Will", "Grizzly Bears", "Llanowar Elves", *mine], theirs=["Llanowar Elves", *theirs], forests=12)
    grave(s, "Grizzly Bears")
    to_hand(s, "Yawgmoth's Will")
    mana(s, B=1, G=2)
    cast(s, "Yawgmoth's Will")
    return s


def kill(s, c, *, answer=True):
    """Lethal damage and the state-based action that follows (704.5g); ``answer``: whatever it asks is answered with its first option."""
    act(s, "p1", type="set_damage", card_ids=[c.id], value=9)
    act(s, s.state.rules.priority, type="pass_priority")
    if answer:
        settle(s)


def test_yawgmoths_will_exiles_itself_and_every_card_of_yours_that_would_go_to_your_graveyard(cards):
    """608.2n: the spell is put into the graveyard as the last part of its resolution, after its own replacement began (614.1a); a creature that dies,
    milled cards and discarded cards are exiled too, from the battlefield, the library and the hand."""
    s = will_table(cards, mine=["Thought Scour", "Mind Rot"])
    assert zone_of(s, "Yawgmoth's Will") == "p1:exile"  # "that card" includes this spell
    elves = put(s, "Llanowar Elves")
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:exile"
    milled = list(s.state.zones["p1:library"][:2])
    to_hand(s, "Thought Scour")
    mana(s, U=1)
    cast(s, "Thought Scour", targets=["p1"])
    assert [s.state.cards[c].zone for c in milled] == ["p1:exile", "p1:exile"]  # 701.17: milled, and exiled instead
    to_hand(s, "Mind Rot")
    mana(s, B=1, G=2)
    for cid in list(s.state.zones["p1:library"][:2]):
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "hand"})
    hand = set(s.state.zones["p1:hand"]) - {card_named(s, "Mind Rot").id}
    cast(s, "Mind Rot", targets=["p1"])
    discarded = hand - set(s.state.zones["p1:hand"])
    assert len(discarded) == 2 and all(s.state.cards[c].zone == "p1:exile" for c in discarded)  # 701.9: discarded, and exiled instead
    assert names(s, "graveyard") == ["Grizzly Bears"]  # (it was there before: nothing is put into it)
    check(s)


def test_yawgmoths_will_is_about_your_graveyard_and_cards_only(cards):
    """"your graveyard": Bob's dying creature goes to Bob's graveyard; 111.1: a token isn't a card (it ceases to exist, never exiled)."""
    s = will_table(cards)
    bob_elves = put(s, "Llanowar Elves", "p2")
    kill(s, bob_elves)
    assert s.state.cards[bob_elves.id].zone == "p2:graveyard"
    act(s, "p1", type="create_token", player="p1", token={"name": "Rat", "type_line": "Token Creature — Rat", "power": "1", "toughness": "1"})
    rat = next(c for c in s.state.cards.values() if c.name == "Rat")
    kill(s, rat)
    assert rat.id not in s.state.cards and not [c for c in s.state.cards.values() if c.name == "Rat"]
    assert "Rat" not in names(s, "exile")
    check(s)


def test_yawgmoths_will_ends_with_the_turn(cards):
    s = will_table(cards)
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1")
    elves = put(s, "Llanowar Elves", "p2" if s.state.turn.active_player == "p2" else "p1")
    kill(s, elves)
    assert s.state.cards[elves.id].zone.endswith(":graveyard")
    check(s)


def test_gaeas_will_exiles_itself_and_a_dying_creature(cards):
    s = build(cards, ["Gaea's Will", "Llanowar Elves"], forests=12)
    to_hand(s, "Gaea's Will")
    mana(s, G=3)
    cast(s, "Gaea's Will")
    elves = put(s, "Llanowar Elves")
    kill(s, elves)
    assert zone_of(s, "Gaea's Will") == "p1:exile" and s.state.cards[elves.id].zone == "p1:exile"
    check(s)


def test_forgotten_cellar_exiles_what_would_go_to_your_graveyard_when_its_door_is_unlocked(cards):
    """Casting the half unlocks that door as the Room enters; its trigger resolves with no "may" the exile could be declined with (the ruling: cards
    that would be put into your graveyard this turn are exiled even if you didn't play them)."""
    s = build(cards, ["Walk-In Closet // Forgotten Cellar", "Llanowar Elves"], forests=12)
    to_hand(s, "Walk-In Closet // Forgotten Cellar")
    mana(s, B=2, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Walk-In Closet // Forgotten Cellar").id, face=1)
    settle(s)
    assert zone_of(s, "Walk-In Closet // Forgotten Cellar") == "p1:battlefield"
    elves = put(s, "Llanowar Elves")
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:exile"
    check(s)


def test_magus_of_the_will_exiles_what_would_go_to_your_graveyard_after_it_is_sacrificed_to_itself(cards):
    """An activated ability: the replacement begins as the ability resolves (611.2a), not as a spell does."""
    s = build(cards, ["Magus of the Will", "Llanowar Elves"], forests=12)
    magus = put(s, "Magus of the Will")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (no longer summoning sick)
    mana(s, B=1, G=2)
    activate(s, "p1", magus)
    settle(s)
    assert s.state.cards[magus.id].zone == "p1:exile"
    elves = put(s, "Llanowar Elves")
    kill(s, elves)
    assert s.state.cards[elves.id].zone == "p1:exile"
    check(s)


def test_a_commander_exiled_by_yawgmoths_will_may_go_to_the_command_zone(cards):
    """903.9a: a commander put into exile may be put into the command zone instead; the replacement exiled it first, then the owner decides."""
    s = will_table(cards)
    krenko = put(s, "Krenko, Mob Boss")
    kill(s, krenko, answer=False)
    d = s.state.rules.decision
    assert s.state.cards[krenko.id].zone == "p1:exile" and d is not None and d.kind == "confirm" and "command zone" in d.prompt
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.cards[krenko.id].zone == "p1:command"
    check(s)


def test_a_commander_may_stay_in_exile_under_yawgmoths_will(cards):
    s = will_table(cards)
    krenko = put(s, "Krenko, Mob Boss")
    kill(s, krenko, answer=False)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[krenko.id].zone == "p1:exile"
    check(s)


# -- Danitha: "from your hand or graveyard" (a hidden zone and a public one, 400.2) ---------------------------------------
def danitha_asked(cards, *, hand=("Pacifism",), graveyard=("Bonesplitter",), forests_in_hand=0):
    """Alice casts Danitha with these cards in her hand / graveyard; the table stops at the question her enters trigger asks."""
    s = build(cards, ["Danitha, Benalia's Hope", "Pacifism", "Bonesplitter"], forests=12)
    for name in graveyard:
        grave(s, name)
    for name in hand:
        to_hand(s, name)
    for cid in [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:forests_in_hand]:
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "hand"})
    to_hand(s, "Danitha, Benalia's Hope")
    mana(s, W=2, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Danitha, Benalia's Hope").id)
    return s, until_asked(s)


def test_danitha_puts_an_aura_from_the_hand_onto_the_battlefield_attached_to_her(cards):
    s, d = danitha_asked(cards)
    assert d is not None and d.player == "p1" and {o.label for o in d.options} == {"Pacifism", "Bonesplitter"}
    pacifism = card_named(s, "Pacifism")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pacifism.id])
    settle(s)
    assert s.state.cards[pacifism.id].zone == "p1:battlefield" and s.state.cards[pacifism.id].attached_to == card_named(s, "Danitha, Benalia's Hope").id
    assert zone_of(s, "Bonesplitter") == "p1:graveyard"
    check(s)


def test_danitha_puts_an_equipment_from_the_graveyard_onto_the_battlefield_attached_to_her(cards):
    s, d = danitha_asked(cards)
    bones = card_named(s, "Bonesplitter")
    before = oid(s, bones)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bones.id])
    settle(s)
    assert s.state.cards[bones.id].zone == "p1:battlefield" and s.state.cards[bones.id].attached_to == card_named(s, "Danitha, Benalia's Hope").id
    assert oid(s, bones) != before  # 400.7
    assert zone_of(s, "Pacifism") == "p1:hand"
    check(s)


def test_danitha_may_put_nothing(cards):
    s, d = danitha_asked(cards)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert zone_of(s, "Pacifism") == "p1:hand" and zone_of(s, "Bonesplitter") == "p1:graveyard"
    check(s)


def test_danitha_asks_whenever_the_hand_holds_cards_so_the_question_hides_the_hand(cards):
    """400.2: a graveyard with no match and a hand with none look the same to the other players as a hand with one: the question is asked either way, and
    the others see only that Alice is choosing (never the options or the prompt)."""
    asked = []
    for hand in (("Pacifism",), ()):
        s, d = danitha_asked(cards, hand=hand, graveyard=(), forests_in_hand=1)
        assert d is not None and d.player == "p1", hand  # (a Forest is in the hand: asked whether or not it holds an Aura)
        assert [o.label for o in d.options] == (["Pacifism"] if hand else [])
        seen = {v: s.view(v)["rules"]["decision"] for v in ("p2", SPECTATOR)}
        asked.append({v: {k: x for k, x in seen[v].items() if k != "id"} for v in seen})
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
        settle(s)
        check(s)
    assert asked[0] == asked[1]
    assert all("Pacifism" not in json.dumps(v) for v in asked[0].values())


def test_danitha_asks_nothing_when_the_hand_is_empty_and_the_graveyard_has_no_match(cards):
    """Nothing is hidden then: no hand to hold a card, and the graveyard is public."""
    s, d = danitha_asked(cards, hand=(), graveyard=())
    assert d is None and "Danitha, Benalia's Hope" in names(s, "battlefield")
    check(s)


# -- Remand: the countered spell goes to its owner's hand (608.2c, 400.3) -----------------------------------------------
def test_remand_puts_the_countered_spell_into_its_owners_hand_and_draws(cards):
    s = build(cards, ["Lightning Bolt"], ["Remand"])
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Remand", "p2")
    mana(s, "p2", U=2)
    mana(s, R=1)
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert s.state.rules.priority == "p2"
    hand_before = len(s.state.zones["p2:hand"])
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Remand", "p2").id, targets=[bolt.id])
    settle(s)
    assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:hand"  # countered, and back in Alice's hand rather than her graveyard
    assert len(s.state.zones["p2:hand"]) == hand_before - 1 + 1  # Remand left the hand; Bob drew a card
    assert zone_of(s, "Remand", "p2") == "p2:graveyard"
    check(s)


# -- Betor: a limit read from how much life was lost (107.3c, 603.3d) ---------------------------------------------------
def test_betor_returns_a_creature_with_mana_value_up_to_the_life_lost_this_turn(cards):
    """"mana value less than or equal to the amount of life you lost this turn": 3 life lost to Lightning Bolt, so Kitchen Finks (3) but not Bloodbraid Elf
    (4); the target is chosen as the end step trigger goes on the stack."""
    s = build(cards, ["Betor, Ancestor's Voice", "Lightning Bolt", "Grizzly Bears", "Kitchen Finks", "Bloodbraid Elf"], forests=12)
    put(s, "Betor, Ancestor's Voice")
    for name in ("Grizzly Bears", "Kitchen Finks", "Bloodbraid Elf"):
        grave(s, name)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p1"])
    assert life(s) == 37
    d = ask(s)
    assert d.player == "p1" and {o.label for o in d.options} == {"Grizzly Bears", "Kitchen Finks"}
    finks = card_named(s, "Kitchen Finks")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[finks.id])
    settle(s)
    assert s.state.cards[finks.id].zone == "p1:battlefield" and zone_of(s, "Bloodbraid Elf") == "p1:graveyard"
    check(s)


# -- Xu-Ifit: "It's a Skeleton in addition to its other types and has no abilities." (613.1d, 613.1f) -------------------
def test_xu_ifits_creature_returns_as_a_skeleton_without_abilities(cards):
    s = build(cards, ["Xu-Ifit, Osteoharmonist", "Kitchen Finks"], forests=12)
    xu = put(s, "Xu-Ifit, Osteoharmonist")
    finks = grave(s, "Kitchen Finks")
    before = oid(s, finks)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # (Xu-Ifit has been here since Alice's last turn)
    activate(s, "p1", xu, targets=[finks.id])
    settle(s)
    back = s.state.cards[finks.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(back)
    assert back.zone == "p1:battlefield" and oid(s, finks) != before  # 400.7
    assert "Skeleton" in ch.subtypes and "Ouphe" in ch.subtypes and "Creature" in ch.types  # in addition to its other types
    assert not ch.abilities and not ch.keywords  # no abilities: no persist, no "enters" gain-life trigger
    check(s)


# -- Geth, Nurgle's Conscription: "that player" is whose graveyard the card was in (400.3) ----------------------------
def test_geth_puts_a_card_from_an_opponents_graveyard_onto_the_battlefield_and_that_player_mills(cards):
    s = build(cards, ["Geth, Lord of the Vault"], ["Grizzly Bears"], forests=12)
    geth = put(s, "Geth, Lord of the Vault")
    bears = grave(s, "Grizzly Bears", "p2")
    library = len(s.state.zones["p2:library"])
    mana(s, B=1, G=2)
    activate(s, "p1", geth, targets=[bears.id], x_value=2)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].tapped and s.state.cards[bears.id].owner == "p2"
    assert len(s.state.zones["p2:library"]) == library - 2  # Bob (the owner), not Alice, mills X cards
    assert len(s.state.zones["p1:library"]) == len(s.state.zones["p1:library"])  # (Alice's own library is the one nobody milled)
    check(s)


def test_nurgles_conscription_exiles_the_graveyard_of_the_player_whose_card_it_took(cards):
    s = build(cards, ["Nurgle's Conscription", "Kitchen Finks"], ["Grizzly Bears", "Llanowar Elves"], forests=12)
    bears = grave(s, "Grizzly Bears", "p2")
    grave(s, "Llanowar Elves", "p2")
    finks = grave(s, "Kitchen Finks")
    before = oid(s, bears)
    to_hand(s, "Nurgle's Conscription")
    mana(s, B=2, G=3)
    cast(s, "Nurgle's Conscription", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1" and s.state.cards[bears.id].tapped
    assert oid(s, bears) != before  # 400.7
    assert names(s, "graveyard", "p2") == [] and sorted(names(s, "exile", "p2")) == ["Llanowar Elves"]
    assert s.state.cards[finks.id].zone == "p1:graveyard"  # (Bob's graveyard, not Alice's)
    check(s)
