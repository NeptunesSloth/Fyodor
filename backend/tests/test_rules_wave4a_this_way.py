"""-- "this way" outcomes (wave 4A) -- counts and conditions on what an earlier instruction of the same spell or
ability actually did ("for each creature destroyed this way", "If a creature is destroyed this way, …", "For each
permanent put into a graveyard this way, its controller creates …"), counters with their own destination ("If
that spell is countered this way, exile it instead …") and the reveal-or-tapped lands (Snarls). Read against CR
2026-09-25: 608.2c/608.2h (the text read as a whole; information from an object as it last existed), 400.7j /
701.17c (a moved card found where it went), 701.8a-b (destroy; indestructible and regeneration), 701.19a,
614.6, 111.1 (a token isn't a card), 108.4a, 614.1c / 614.12a (choices as a permanent enters), 701.20a-b
(reveal). The cards are real Commander cards, their Oracle text transcribed from the card database. Every
scenario checks that replaying the recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts, this_way
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import replay_matches

REAL = [
    card('Fumigate', set_code="tst", number="W1", mana_cost='{3}{W}{W}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy all creatures. You gain 1 life for each creature destroyed this way.', colors=['W'], color_identity=['W']),
    card('Blood Money', set_code="tst", number="W2", mana_cost='{5}{B}{B}', cmc=7.0, type_line='Sorcery', oracle_text='Destroy all creatures. For each nontoken creature destroyed this way, you create a tapped Treasure token.', colors=['B'], color_identity=['B'], keywords=['Treasure']),
    card("Kaya's Wrath", set_code="tst", number="W3", mana_cost='{W}{W}{B}{B}', cmc=4.0, type_line='Sorcery', oracle_text='Destroy all creatures. You gain life equal to the number of creatures you controlled that were destroyed this way.', colors=['B', 'W'], color_identity=['B', 'W']),
    card('Gorging Vulture', set_code="tst", number="W4", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Bird', oracle_text='Flying\nWhen this creature enters, mill four cards. You gain 1 life for each creature card milled this way. (To mill four cards, put the top four cards of your library into your graveyard.)', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Flying', 'Mill']),
    card('Voracious Fell Beast', set_code="tst", number="W5", mana_cost='{4}{B}{B}', cmc=6.0, type_line='Creature — Drake Beast', oracle_text='Flying\nWhen this creature enters, each opponent sacrifices a creature of their choice. Create a Food token for each creature sacrificed this way. (It\'s an artifact with "{2}, {T}, Sacrifice this token: You gain 3 life.")', power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=['Flying', 'Food']),
    card('Terastodon', set_code="tst", number="W6", mana_cost='{6}{G}{G}', cmc=8.0, type_line='Creature — Elephant', oracle_text='When this creature enters, you may destroy up to three target noncreature permanents. For each permanent put into a graveyard this way, its controller creates a 3/3 green Elephant creature token.', power='9', toughness='9', colors=['G'], color_identity=['G']),
    card('Noxious Gearhulk', set_code="tst", number="W7", mana_cost='{4}{B}{B}', cmc=6.0, type_line='Artifact Creature — Construct', oracle_text='Menace\nWhen this creature enters, you may destroy another target creature. If a creature is destroyed this way, you gain life equal to its toughness.', power='5', toughness='4', colors=['B'], color_identity=['B'], keywords=['Menace']),
    card('Memory Lapse', set_code="tst", number="W8", mana_cost='{1}{U}', cmc=2.0, type_line='Instant', oracle_text="Counter target spell. If that spell is countered this way, put it on top of its owner's library instead of into that player's graveyard.", colors=['U'], color_identity=['U']),
    card('Dissipate', set_code="tst", number="W9", mana_cost='{1}{U}{U}', cmc=3.0, type_line='Instant', oracle_text="Counter target spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.", colors=['U'], color_identity=['U']),
    card('Choked Estuary', set_code="tst", number="W10", mana_cost='', cmc=0.0, type_line='Land', oracle_text="As this land enters, you may reveal an Island or Swamp card from your hand. If you don't, this land enters tapped.\n{T}: Add {U} or {B}.", color_identity=['B', 'U']),
    card('Bonehoard Dracosaur', set_code="tst", number="W11", mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Dinosaur Dragon', oracle_text='Flying, first strike\nAt the beginning of your upkeep, exile the top two cards of your library. You may play them this turn. If you exiled a land card this way, create a 3/1 red Dinosaur creature token. If you exiled a nonland card this way, create a Treasure token.', power='5', toughness='5', colors=['R'], color_identity=['R'], keywords=['Flying', 'First strike', 'Treasure']),
    card('Paradoxical Outcome', set_code="tst", number="W12", mana_cost='{3}{U}', cmc=4.0, type_line='Instant', oracle_text="Return any number of target nonland, nontoken permanents you control to their owners' hands. Draw a card for each card returned to your hand this way.", colors=['U'], color_identity=['U']),
    card('Darksteel Myr', set_code="tst", number="W13", mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Myr', oracle_text='Indestructible (Damage and effects that say "destroy" don\'t destroy this creature. If its toughness is 0 or less, it still dies.)', power='0', toughness='1', keywords=['Indestructible']),
    card('Coerced Confession', set_code="tst", number="W15", mana_cost='{4}{U/B}', cmc=5.0, type_line='Sorcery', oracle_text='Target player mills four cards. You draw a card for each creature card put into their graveyard this way.', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Mill']),
    card('Come Back Wrong', set_code="tst", number="W16", mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Destroy target creature. If a creature card is put into a graveyard this way, return it to the battlefield under your control. Sacrifice it at the beginning of your next end step.', colors=['B'], color_identity=['B']),
    card('Swamp', set_code="tst", number="W17", type_line='Basic Land — Swamp', oracle_text='({T}: Add {B}.)', color_identity=['B']),
    card('Windfall', set_code="tst", number="V1", mana_cost='{2}{U}', cmc=3.0, type_line='Sorcery', oracle_text='Each player discards their hand, then draws cards equal to the greatest number of cards a player discarded this way.', colors=['U'], color_identity=['U']),
    card('Greenwarden of Murasa', set_code="tst", number="V2", mana_cost='{4}{G}{G}', cmc=6.0, type_line='Creature — Elemental', oracle_text='When this creature enters, you may return target card from your graveyard to your hand.\nWhen this creature dies, you may exile it. If you do, return target card from your graveyard to your hand.', power='5', toughness='4', colors=['G'], color_identity=['G']),
    card('Victimize', set_code="tst", number="V3", mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Choose two target creature cards in your graveyard. Sacrifice a creature. If you do, return the chosen cards to the battlefield tapped.', colors=['B'], color_identity=['B']),
    card('Siege Striker', set_code="tst", number="V4", mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Human Soldier', oracle_text='Double strike (This creature deals both first-strike and regular combat damage.)\nWhenever this creature attacks, you may tap any number of untapped creatures you control. This creature gets +1/+1 until end of turn for each creature tapped this way.', power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=['Double strike']),
    card('Harmony of Nature', set_code="tst", number="V5", mana_cost='{2}{G}', cmc=3.0, type_line='Sorcery', oracle_text='Tap any number of untapped creatures you control. You gain 4 life for each creature tapped this way.', colors=['G'], color_identity=['G']),
    card("Wit's End", set_code="tst", number="V6", mana_cost='{5}{B}{B}', cmc=7.0, type_line='Sorcery', oracle_text='Target player discards their hand.', colors=['B'], color_identity=['B']),
]

NAMES = [c["name"] for c in REAL if c["name"] != "Swamp"]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, players=2):
    names = ["Alice", "Bob", "Carol"][:players]
    commanders = ["Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss"][:players]
    decks = [deck(cards, commanders[0], [*((1, n) for n in NAMES), (1, "Albino Troll"), (3, "Grizzly Bears"),
                                         (2, "Lightning Bolt"), (3, "Island"), (3, "Swamp"), (10, "Forest")])]
    decks += [deck(cards, c, [(3, "Grizzly Bears"), (1, "Sol Ring"), (1, "Lightning Bolt"), (1, "Memory Lapse"),
                              (1, "Dissipate"), (20, "Island")]) for c in commanders[1:]]
    state = new_game([PlayerSetup(n, cards=d) for n, d in zip(names, decks, strict=True)], shuffle=False)
    s = GameSession(enable(state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def put(s, name, zone_name, pid="p1", nth=0):
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(("library", "hand"))
             and c.zone != f"{pid}:{zone_name}"]
    c = sorted(found, key=lambda c: not c.zone.endswith("library"))[nth]  # (from the library first)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": zone_name, "player": pid})
    return s.state.cards[c.id]


def on_top(s, names, pid="p1"):
    """Put these library cards on top of the library, the first named on top."""
    used: set[str] = set()
    for name in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"
                 and c.id not in used)
        used.add(c.id)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library", "player": pid}, index=0)
    assert [s.state.cards[c].name for c in zone(s.state, pid, "library")[:len(names)]] == names


def token(s, pid, name, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                        "toughness": t, "text": text})
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid][-1]


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def life(s, pid="p1"):
    return s.state.players[pid].life


def resolve(s, picks=()):
    """Pass priority until the stack is empty, answering each decision with the first of ``picks`` that is an
    option (or declining an optional question)."""
    picks = list(picks)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [p for p in picks if p in ids]
            if want and d.max_choices and d.max_choices > 1:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=want[:d.max_choices])
                picks = [p for p in picks if p not in want]
            elif want:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[want[0]])
                picks.remove(want[0])
            elif "yes" in ids:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
            else:
                raise AssertionError(f"unexpected decision {d.kind}: {d.prompt} {ids}")
            continue
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never resolved")


def roundtrip(s):
    replay_matches(s)  # (reload: the history rebuilds the same table)
    assert GameState.model_validate(s.state.model_dump(mode="json")).model_dump(mode="json") == s.state.model_dump(mode="json")


def level(cards, name):
    return coverage.of_characteristics(printed_from_data(cards.resolve(name), 0)).level


def cast(s, name, targets=(), pid="p1", target_counts=None, **m):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(("library", "hand")))
    if c.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand", "player": pid})
    mana(s, pid, **m)
    extra: dict = {"targets": list(targets)} if targets else {}
    if target_counts is not None:
        extra["target_counts"] = target_counts
    act(s, pid, type="cast_spell", card_id=c.id, **extra)
    return c


def named(s, name, zone_suffix, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(zone_suffix)
            and (pid is None or c.zone.startswith(f"{pid}:"))]


# -- grammar ---------------------------------------------------------------------------------------
def test_the_new_wordings_are_covered(cards):
    for name in NAMES:
        assert level(cards, name) == "FULL", name


def test_counts_parse_to_the_instruction_they_name():
    found = scripts.parse_effects("Destroy all creatures. You gain 1 life for each creature destroyed this way.")
    assert found is not None
    destroy, gain = found[0]
    assert destroy["as"] == "e0" and gain["n"] == {"ref_count": "e0", "this_way": "destroyed", "of": gain["n"]["of"]}
    # "For each …, you create …" reads as the instruction with its multiplier
    found = scripts.parse_effects("Mill three cards. For each creature card milled this way, create a 2/2 black Zombie "
                                  "creature token.")
    assert found is not None and found[0][1]["n"]["this_way"] == "milled"
    assert this_way.parse("creatures they controlled that were destroyed this way") is None  # (each player's own count)


def test_unread_forms_stay_manual():
    # a count with no instruction of that verb before it
    assert scripts.parse_effects("Draw a card for each creature destroyed this way.") is None
    # "its controller" for each object, with a different instruction than creating tokens, drawing, cloaking or investigating (wave 52A: those are read now)
    assert scripts.parse_effects("Destroy all creatures. For each creature destroyed this way, its controller gains 1 life.") is None
    # (wave 19C: "you discarded" after every player discarded is read now: only the cards the controller discarded count —
    # a discarded card is its owner's, 701.9a — tests/test_rules_wave19c_ifyoudo.py)
    assert this_way.condition("you discarded a land card this way")["value"]["by"] == "you"
    # a counter's destination after anything but a counter
    assert scripts.parse_effects("Draw a card. If that spell is countered this way, exile it instead of putting it into its "
                                 "owner's graveyard.") is None


# -- 701.8: what a destroy actually destroyed ------------------------------------------------------
def test_fumigate_counts_only_creatures_actually_destroyed(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "battlefield")
    myr = put(s, "Darksteel Myr", "battlefield")  # indestructible: not destroyed (701.8b)
    troll = put(s, "Albino Troll", "battlefield")
    tok = token(s, "p2", "Wolf")
    mana(s, G=2)
    act(s, "p1", type="activate_ability", card_id=troll.id, ability=1)  # {1}{G}: regenerate (701.19a: replaced, not destroyed)
    resolve(s)
    cast(s, "Fumigate", W=2, C=3)
    resolve(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[myr.id].zone == "p1:battlefield"
    assert s.state.cards[troll.id].zone == "p1:battlefield"  # regenerated
    assert tok.id not in s.state.cards or not s.state.cards[tok.id].zone.endswith("battlefield")
    assert life(s) == 40 + 2  # the Bears and the Wolf token
    roundtrip(s)


def test_blood_money_reads_nontoken_from_last_known_information(cards):
    s = build(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Grizzly Bears", "battlefield", pid="p2")
    token(s, "p2", "Wolf")
    cast(s, "Blood Money", B=2, C=5)
    resolve(s)
    treasures = named(s, "Treasure", "battlefield", "p1")
    assert len(treasures) == 2 and all(t.tapped for t in treasures)  # two nontoken creatures; the token isn't counted
    roundtrip(s)


def test_kayas_wrath_counts_the_creatures_you_controlled(cards):
    s = build(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Grizzly Bears", "battlefield", nth=1)
    put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Kaya's Wrath", W=2, B=2)
    resolve(s)
    assert life(s) == 42 and life(s, "p2") == 40
    roundtrip(s)


# -- 701.17c: milled cards, found where they went --------------------------------------------------
def test_gorging_vulture_counts_creature_cards_milled(cards):
    s = build(cards)
    on_top(s, ["Grizzly Bears", "Island", "Grizzly Bears", "Forest"])
    cast(s, "Gorging Vulture", B=1, C=2)
    resolve(s)
    assert len(zone(s.state, "p1", "graveyard")) == 4
    assert life(s) == 42
    roundtrip(s)


def test_coerced_confession_counts_the_target_players_milled_creatures(cards):
    s = build(cards)
    on_top(s, ["Grizzly Bears", "Island", "Sol Ring", "Grizzly Bears"], pid="p2")
    hand = len(zone(s.state, "p1", "hand"))
    cast(s, "Coerced Confession", targets=["p2"], B=1, C=4)
    resolve(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 2  # (the spell came from the library) two creature cards milled
    assert len(zone(s.state, "p2", "graveyard")) == 4
    roundtrip(s)


# -- edicts: what each opponent sacrificed -----------------------------------------------------------
def test_voracious_fell_beast_makes_a_food_per_creature_sacrificed(cards):
    s = build(cards, players=3)
    bob1 = put(s, "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Grizzly Bears", "battlefield", pid="p2", nth=1)
    cast(s, "Voracious Fell Beast", B=2, C=4)
    resolve(s, [bob1.id])  # Bob chooses which Bears; Carol has no creature
    assert s.state.cards[bob1.id].zone == "p2:graveyard"
    assert len(named(s, "Food", "battlefield", "p1")) == 1
    roundtrip(s)


# -- conditions and per-controller creations ---------------------------------------------------------
def test_noxious_gearhulk_gains_the_destroyed_creatures_toughness(cards):
    s = build(cards)
    troll = put(s, "Albino Troll", "battlefield")
    cast(s, "Noxious Gearhulk", B=2, C=4)
    resolve(s, [troll.id])
    assert s.state.cards[troll.id].zone == "p1:graveyard" and life(s) == 43  # its toughness, as it last existed
    roundtrip(s)


def test_noxious_gearhulk_gains_nothing_when_nothing_was_destroyed(cards):
    s = build(cards)
    myr = put(s, "Darksteel Myr", "battlefield")
    cast(s, "Noxious Gearhulk", B=2, C=4)
    resolve(s, [myr.id])
    assert s.state.cards[myr.id].zone == "p1:battlefield" and life(s) == 40
    roundtrip(s)


def test_terastodon_gives_each_controller_an_elephant_per_permanent_put_into_a_graveyard(cards):
    s = build(cards)
    mine = put(s, "Swamp", "battlefield")
    ring = put(s, "Sol Ring", "battlefield", pid="p2")
    island = put(s, "Island", "battlefield", pid="p2")
    cast(s, "Terastodon", G=2, C=6)
    resolve(s, [mine.id, ring.id, island.id])
    assert len(named(s, "Elephant", "battlefield", "p1")) == 1
    assert len(named(s, "Elephant", "battlefield", "p2")) == 2
    roundtrip(s)


def test_come_back_wrong_returns_only_a_creature_card(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Come Back Wrong", targets=[bears.id], B=1, C=2)
    resolve(s)
    back = s.state.cards[bears.id]
    assert back.zone == "p1:battlefield" and back.controller == "p1"  # under Alice's control
    roundtrip(s)


def test_come_back_wrong_on_a_token_returns_nothing(cards):
    s = build(cards)
    wolf = token(s, "p2", "Wolf")
    cast(s, "Come Back Wrong", targets=[wolf.id], B=1, C=2)
    resolve(s)
    assert not named(s, "Wolf", "battlefield")  # a token isn't a card (111.1)
    roundtrip(s)


def test_bonehoard_dracosaur_reads_what_it_exiled(cards):
    s = build(cards)
    put(s, "Bonehoard Dracosaur", "battlefield")
    on_top(s, ["Island", "Grizzly Bears"])
    for _ in range(80):  # to Alice's next upkeep trigger
        if s.state.turn.number == 3 and s.state.turn.phase != "beginning":
            break
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    resolve(s)
    assert len(named(s, "Dinosaur", "battlefield", "p1")) == 1 and len(named(s, "Treasure", "battlefield", "p1")) == 1
    roundtrip(s)


def test_paradoxical_outcome_counts_cards_returned_to_your_hand(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Darksteel Myr", "battlefield")
    hand = len(zone(s.state, "p1", "hand"))
    cast(s, "Paradoxical Outcome", targets=[a.id, b.id], target_counts=[2], U=1, C=3)
    resolve(s)
    assert s.state.cards[a.id].zone == "p1:hand" and s.state.cards[b.id].zone == "p1:hand"
    assert len(zone(s.state, "p1", "hand")) == hand + 2 + 2  # (the spell came from the library) two back, two drawn
    roundtrip(s)


# -- 608.2c: a counter's own destination ------------------------------------------------------------
def _bolt_then_counter(s, counter, **m):
    """Alice casts Lightning Bolt at Bob; Bob counters it with ``counter``."""
    answer = put(s, counter, "hand", pid="p2")  # (in hand with Islands open: Bob can respond, so he gets priority)
    for _ in range(sum(m.values())):
        put(s, "Island", "battlefield", pid="p2", nth=0)
    bolt = cast(s, "Lightning Bolt", targets=["p2"], R=1)
    assert s.state.zones["stack"] == [bolt.id] and s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=answer.id, targets=[bolt.id])
    resolve(s)
    assert life(s, "p2") == 40
    return s.state.cards[bolt.id]


def test_memory_lapse_puts_the_spell_on_top_of_its_owners_library(cards):
    s = build(cards)
    bolt = _bolt_then_counter(s, "Memory Lapse", U=1, C=1)
    assert zone(s.state, "p1", "library")[0] == bolt.id
    roundtrip(s)


def test_dissipate_exiles_the_countered_spell(cards):
    s = build(cards)
    bolt = _bolt_then_counter(s, "Dissipate", U=2, C=1)
    assert bolt.zone == "p1:exile"
    roundtrip(s)


# -- 614.12a / 701.20a: the reveal-or-tapped lands ---------------------------------------------------
def _estuary_in_hand(s):
    land = next(c for c in s.state.cards.values() if c.name == "Choked Estuary")
    act(s, "p1", type="move", card_ids=[land.id], to={"zone": "hand", "player": "p1"})
    return land


def test_snarl_enters_untapped_when_a_matching_card_is_revealed(cards):
    s = build(cards)
    land = _estuary_in_hand(s)
    island = put(s, "Island", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and island.id in {o.id for o in d.options}
    bob = s.view("p2")["rules"]["decision"]  # Bob sees only that Alice is choosing (the hand stays hidden)
    assert "options" not in bob and island.id not in json.dumps(bob)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[island.id])
    assert s.state.cards[land.id].zone == "p1:battlefield" and not s.state.cards[land.id].tapped
    assert s.state.cards[island.id].zone == "p1:hand" and not s.state.cards[island.id].revealed_to  # shown, then hidden
    assert "Island" in json.dumps(s.view("p2")["log"])  # everyone saw what was revealed
    roundtrip(s)


def test_snarl_enters_tapped_when_declined_or_with_nothing_to_reveal(cards):
    s = build(cards)
    land = _estuary_in_hand(s)
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand" and c.name in ("Island", "Swamp")]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library", "player": "p1"})
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.rules.decision is None  # nothing else in hand (its size is public): no question
    assert s.state.cards[land.id].tapped
    roundtrip(s)
    s = build(cards)
    land = _estuary_in_hand(s)
    put(s, "Swamp", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["none"])
    assert s.state.cards[land.id].zone == "p1:battlefield" and s.state.cards[land.id].tapped
    roundtrip(s)


# -- review (wave 4R) -- hidden information: with cards in hand but none matching, Alice is still asked (only "Don't
# reveal" offered), so whether she was asked tells Bob nothing about her hand
def test_snarl_asks_even_without_a_matching_card_in_a_nonempty_hand(cards):
    s = build(cards)
    land = _estuary_in_hand(s)
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand" and c.name in ("Island", "Swamp")]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library", "player": "p1"})
    put(s, "Forest", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["none"]
    bob = s.view("p2")["rules"]["decision"]
    assert "options" not in bob
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["none"])
    assert s.state.cards[land.id].tapped
    roundtrip(s)


# -- 701.9a: discarding a hand ---------------------------------------------------------------------
def test_windfall_draws_the_greatest_number_any_player_discarded(cards):
    s = build(cards)
    for name in ("Island", "Swamp", "Forest"):
        put(s, name, "hand")
    put(s, "Island", "hand", pid="p2")
    cast(s, "Windfall", U=1, C=2)
    resolve(s)
    assert len(zone(s.state, "p1", "hand")) == 3 and len(zone(s.state, "p2", "hand")) == 3
    assert len(zone(s.state, "p1", "graveyard")) == 4 and len(zone(s.state, "p2", "graveyard")) == 1  # (and Windfall)
    roundtrip(s)


def test_wits_end_discards_the_whole_hand_without_a_choice(cards):
    s = build(cards)
    for _ in range(3):
        put(s, "Island", "hand", pid="p2")
    cast(s, "Wit's End", targets=["p2"], B=2, C=5)
    resolve(s)
    assert zone(s.state, "p2", "hand") == [] and len(zone(s.state, "p2", "graveyard")) == 3
    roundtrip(s)


# -- "If you do" after an optional action, with a target of its own (603.3d, 608.2b) -------------------
def test_greenwarden_exiles_itself_to_return_a_card(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    warden = put(s, "Greenwarden of Murasa", "battlefield")
    cast(s, "Fumigate", W=2, C=3)  # it dies
    resolve(s, [bears.id])
    assert s.state.cards[warden.id].zone == "p1:exile" and s.state.cards[bears.id].zone == "p1:hand"
    roundtrip(s)


def test_victimize_returns_both_cards_only_if_a_creature_was_sacrificed(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Grizzly Bears", "graveyard", nth=1)
    troll = put(s, "Albino Troll", "battlefield")
    cast(s, "Victimize", targets=[a.id, b.id], target_counts=[2], B=1, C=2)
    resolve(s)
    assert s.state.cards[troll.id].zone == "p1:graveyard"
    for c in (a, b):
        assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].tapped
    roundtrip(s)
    s = build(cards)  # nothing to sacrifice: nothing returns (608.2c)
    a = put(s, "Grizzly Bears", "graveyard")
    b = put(s, "Grizzly Bears", "graveyard", nth=1)
    cast(s, "Victimize", targets=[a.id, b.id], target_counts=[2], B=1, C=2)
    resolve(s)
    assert s.state.cards[a.id].zone == "p1:graveyard" and s.state.cards[b.id].zone == "p1:graveyard"
    roundtrip(s)


# -- "tap any number of untapped creatures you control" ------------------------------------------------
def test_harmony_of_nature_counts_the_creatures_tapped(cards):
    s = build(cards)
    a = put(s, "Grizzly Bears", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", nth=1)
    c = put(s, "Albino Troll", "battlefield")
    cast(s, "Harmony of Nature", G=1, C=2)
    d = s.state.rules.decision
    for _ in range(5):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d.min_choices == 0 and {o.id for o in d.options} == {a.id, b.id, c.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    resolve(s)
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped and not s.state.cards[c.id].tapped
    assert life(s) == 48
    roundtrip(s)
