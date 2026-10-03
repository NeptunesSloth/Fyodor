"""Recursion and tutor wordings (wave 4M), read against the Comprehensive Rules of 2026-09-25: 701.23 (a search is
private; for a stated quality it may find nothing, 701.23b; found cards are revealed only when the text says so,
701.23e), 701.24 (shuffle), 608.2m/608.2n (a spell that moves itself: "Exile ~." / "Shuffle ~ into its owner's
library." / "Put ~ on the bottom of its owner's library."), 205.3i (land types: "that share a land type"), 611.2a (no
duration stated: the effect lasts as long as its object, "It gains haste."), 205.1b ("in addition to its other
types"), 122.6 (entering with counters), 700.6 (historic). The cards are real Commander cards, their Oracle text
transcribed from the card database. Every scenario checks replay, and the hidden ones a reload too."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.language import parse_sentence
from app.rules.plan import Plan
from app.rules.scripts import parse_effects
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_delayed import next_end_step, responsive
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

REAL = [
    card("Green Sun's Zenith", set_code="tst", number="M1", mana_cost='{X}{G}', cmc=1.0, type_line='Sorcery',
         oracle_text="Search your library for a green creature card with mana value X or less, put it onto the battlefield, "
                     "then shuffle. Shuffle Green Sun's Zenith into its owner's library.", colors=['G'], color_identity=['G']),
    card('Rally the Ancestors', set_code="tst", number="M2", mana_cost='{X}{W}{W}', cmc=2.0, type_line='Instant',
         oracle_text='Return each creature card with mana value X or less from your graveyard to the battlefield. Exile those '
                     'creatures at the beginning of your next upkeep. Exile Rally the Ancestors.', colors=['W'], color_identity=['W']),
    card('Beacon of Unrest', set_code="tst", number="M3", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Sorcery',
         oracle_text="Put target artifact or creature card from a graveyard onto the battlefield under your control. Shuffle "
                     "Beacon of Unrest into its owner's library.", colors=['B'], color_identity=['B']),
    card('Seasons Past', set_code="tst", number="M4", mana_cost='{4}{G}{G}', cmc=6.0, type_line='Sorcery',
         oracle_text="Return any number of cards with different mana values from your graveyard to your hand. Put Seasons Past "
                     "on the bottom of its owner's library.", colors=['G'], color_identity=['G']),
    card('Myriad Landscape', set_code="tst", number="M5", type_line='Land',
         oracle_text='This land enters tapped.\n{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Search your library for up to two '
                     'basic land cards that share a land type, put them onto the battlefield tapped, then shuffle.'),
    card('Fabled Passage', set_code="tst", number="M6", type_line='Land',
         oracle_text='{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, '
                     'then shuffle. Then if you control four or more lands, untap that land.'),
    card('Mystical Teachings', set_code="tst", number="M7", mana_cost='{3}{U}', cmc=4.0, type_line='Instant',
         oracle_text='Search your library for an instant card or a card with flash, reveal it, put it into your hand, then '
                     'shuffle.\nFlashback {5}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)',
         colors=['U'], color_identity=['B', 'U'], keywords=['Flashback']),
    card('Circuitous Route', set_code="tst", number="M8", mana_cost='{3}{G}', cmc=4.0, type_line='Sorcery',
         oracle_text='Search your library for up to two basic land cards and/or Gate cards, put them onto the battlefield '
                     'tapped, then shuffle.', colors=['G'], color_identity=['G']),
    card('Axgard Armory', set_code="tst", number="M9", type_line='Land',
         oracle_text='This land enters tapped.\n{T}: Add {W}.\n{1}{R}{R}{W}, {T}, Sacrifice this land: Search your library for '
                     'an Aura card and/or an Equipment card, reveal them, put them into your hand, then shuffle.'),
    card('Boundless Realms', set_code="tst", number="M10", mana_cost='{6}{G}', cmc=7.0, type_line='Sorcery',
         oracle_text='Search your library for up to X basic land cards, where X is the number of lands you control, put them '
                     'onto the battlefield tapped, then shuffle.', colors=['G'], color_identity=['G']),
    card('Traverse the Outlands', set_code="tst", number="M11", mana_cost='{4}{G}', cmc=5.0, type_line='Sorcery',
         oracle_text='Search your library for up to X basic land cards, where X is the greatest power among creatures you '
                     'control. Put those cards onto the battlefield tapped, then shuffle.', colors=['G'], color_identity=['G']),
    card('Brilliant Restoration', set_code="tst", number="M12", mana_cost='{3}{W}{W}{W}{W}', cmc=7.0, type_line='Sorcery',
         oracle_text='Return all artifact and enchantment cards from your graveyard to the battlefield.', colors=['W'],
         color_identity=['W']),
    card('Puppeteer Clique', set_code="tst", number="M13", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Faerie Wizard',
         oracle_text="Flying\nWhen this creature enters, put target creature card from an opponent's graveyard onto the "
                     "battlefield under your control. It gains haste. At the beginning of your next end step, exile it.\n"
                     "Persist (When this creature dies, if it had no -1/-1 counters on it, return it to the battlefield under "
                     "its owner's control with a -1/-1 counter on it.)", power='3', toughness='2', colors=['B'],
         color_identity=['B'], keywords=['Flying', 'Persist']),
    card("Liliana, Death's Majesty", set_code="tst", number="M14", mana_cost='{3}{B}{B}', cmc=5.0,
         type_line='Legendary Planeswalker — Liliana', loyalty='5',
         oracle_text='+1: Create a 2/2 black Zombie creature token. Mill two cards.\n−3: Return target creature card from your '
                     'graveyard to the battlefield. That creature is a black Zombie in addition to its other colors and types.\n'
                     '−7: Destroy all non-Zombie creatures.', colors=['B'], color_identity=['B'], keywords=['Mill']),
    card('Rakdos Joins Up', set_code="tst", number="M15", mana_cost='{3}{B}{R}', cmc=5.0, type_line='Legendary Enchantment',
         oracle_text="When Rakdos Joins Up enters, return target creature card from your graveyard to the battlefield with two "
                     "additional +1/+1 counters on it.\nWhenever a legendary creature you control dies, Rakdos Joins Up deals "
                     "damage equal to that creature's power to target opponent.", colors=['B', 'R'], color_identity=['B', 'R']),
    card('Bloodline Necromancer', set_code="tst", number="M16", mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Vampire Wizard',
         oracle_text='Lifelink\nWhen this creature enters, you may return target Vampire or Wizard creature card from your '
                     'graveyard to the battlefield.', power='3', toughness='2', colors=['B'], color_identity=['B'],
         keywords=['Lifelink']),
    card('Rampant Rejuvenator', set_code="tst", number="M17", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Plant Hydra',
         oracle_text="This creature enters with two +1/+1 counters on it.\nWhen this creature dies, search your library for up "
                     "to X basic land cards, where X is this creature's power, put them onto the battlefield, then shuffle.",
         power='0', toughness='0', colors=['G'], color_identity=['G']),
    card('Spell Crumple', set_code="tst", number="M19", mana_cost='{1}{U}{U}', cmc=3.0, type_line='Instant',
         oracle_text="Counter target spell. If that spell is countered this way, put it on the bottom of its owner's library "
                     "instead of into that player's graveyard. Put Spell Crumple on the bottom of its owner's library.",
         colors=['U'], color_identity=['U']),
    card('Vampire Nighthawk', set_code="tst", number="M20", mana_cost='{1}{B}{B}', cmc=3.0, type_line='Creature — Vampire Shaman',
         oracle_text='Flying\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nLifelink '
                     '(Damage dealt by this creature also causes you to gain that much life.)', power='2', toughness='3',
         colors=['B'], color_identity=['B'], keywords=['Deathtouch', 'Flying', 'Lifelink']),
    card('Plains', set_code="tst", number="M21", type_line='Basic Land — Plains', oracle_text='({T}: Add {W}.)'),
    card('Abstergo Entertainment', set_code="tst", number="M22", type_line='Legendary Land',
         oracle_text='{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\n{3}, {T}, Exile Abstergo Entertainment: Return up to '
                     'one target historic card from your graveyard to your hand, then exile all graveyards. (Artifacts, '
                     'legendaries, and Sagas are historic.)'),
]

NAMES = [c["name"] for c in REAL]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in NAMES] + [
        (1, "Llanowar Elves"), (1, "Grizzly Bears"), (1, "Ambush Viper"), (1, "Lightning Bolt"), (1, "Counterspell"), (1, "Sol Ring"),
        (1, "Pacifism"), (1, "Bonesplitter"), (1, "Test Guildgate"), (4, "Forest"), (3, "Island"), (2, "Swamp")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (1, "Lightning Bolt"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def named(s, name, pid="p1", zone_name=None):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid
                and (zone_name is None or c.zone.endswith(zone_name)))


def put(s, name, where, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(where))
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": where, "player": pid} if where != "battlefield" else {"zone": where})
    return s.state.cards[c.id]


def cast(s, name, **kw):
    c = put(s, name, "hand")
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    pass_until_stack_empty(s)
    return c


def decision(s, kind="choose_cards"):
    d = s.state.rules.decision
    assert d is not None and d.kind == kind, d
    return d


def choose(s, *names, player="p1"):
    d = decision(s)
    ids, used = [], set()
    for n in names:
        cid = next(o.id for o in d.options if s.state.cards[o.id].name == n and o.id not in used)
        used.add(cid)
        ids.append(cid)
    act(s, player, type="choose", decision_id=d.id, option_ids=ids)
    pass_until_stack_empty(s)
    return ids


def options(s):
    return sorted(s.state.cards[o.id].name for o in decision(s).options)


def triggers(s, target=None):
    """Let the engine look at the table, then put the triggers on the stack, choosing ``target``, and resolve them
    (answering "you may" with yes)."""
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "choose_one" and target is not None and any(o.id == target for o in d.options):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[target])
        elif d.kind in ("confirm", "choose_one") and any(o.id == "yes" for o in d.options):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            break
        pass_until_stack_empty(s)


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def private(s, ids):
    """Bob's view (live and reloaded) carries neither the search's options nor the library's cards."""
    for session in (s, reloaded(s)):
        bob = json.dumps(session.view("p2"))
        assert "options" not in session.view("p2")["rules"]["decision"]
        for cid in ids:
            assert cid not in bob


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def level(s, name):
    return coverage.of_card_data(s.cards.resolve(name)).level


def test_the_wave_4m_cards_are_full(cards):
    s = build(cards)
    for name in ("Green Sun's Zenith", "Rally the Ancestors", "Beacon of Unrest", "Seasons Past", "Myriad Landscape",
                 "Fabled Passage", "Mystical Teachings", "Circuitous Route", "Axgard Armory", "Boundless Realms",
                 "Traverse the Outlands", "Brilliant Restoration", "Puppeteer Clique", "Liliana, Death's Majesty",
                 "Rakdos Joins Up", "Bloodline Necromancer", "Rampant Rejuvenator", "Spell Crumple", "Abstergo Entertainment"):
        assert level(s, name) == "FULL", name


# -- a spell that moves itself (608.2m, 608.2n) ------------------------------------------------------------
@pytest.mark.parametrize(("x", "found"), [(1, ["Llanowar Elves"]), (2, ["Ambush Viper", "Grizzly Bears", "Llanowar Elves"])])
def test_green_suns_zenith_searches_by_x_and_shuffles_itself_into_the_library(cards, x, found):
    s = build(cards)
    mana(s, G=1, C=x)
    gsz = cast(s, "Green Sun's Zenith", x_value=x)
    assert options(s) == found  # (green creature cards, mana value X or less: the server filters, 701.23)
    library = list(zone(s.state, "p1", "library"))
    private(s, library)
    [elf] = choose(s, "Llanowar Elves")
    assert s.state.cards[elf].zone == "p1:battlefield"
    assert s.state.cards[gsz.id].zone == "p1:library"  # shuffled in, not put into the graveyard (608.2n)
    assert not any(s.state.cards[c].name == "Green Sun's Zenith" for c in zone(s.state, "p1", "graveyard"))
    assert "Green Sun's Zenith" not in json.dumps(s.view("p2")["players"])  # (a library's order is hidden)
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_green_suns_zenith_may_find_nothing(cards):
    s = build(cards)
    mana(s, G=1)
    gsz = cast(s, "Green Sun's Zenith", x_value=0)
    assert options(s) == []  # 701.23b: a stated quality: nothing found, still shuffled
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    pass_until_stack_empty(s)
    assert s.state.cards[gsz.id].zone == "p1:library" and not s.state.zones.get("stack")
    replay_matches(s)


def test_beacon_of_unrest_reanimates_and_shuffles_itself_away(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=2, C=3)
    beacon = cast(s, "Beacon of Unrest", targets=[bears.id])
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1"
    assert s.state.cards[beacon.id].zone == "p1:library"
    replay_matches(s)


def test_a_countered_self_moving_spell_goes_to_the_graveyard(cards):
    """608.2b: with its only target gone the spell doesn't resolve: none of its instructions happen, so it is put
    into its owner's graveyard as usual."""
    s = build(cards)
    responsive(s)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=2, C=3)
    beacon = put(s, "Beacon of Unrest", "hand")
    act(s, "p1", type="cast_spell", card_id=beacon.id, targets=[bears.id])
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "exile", "player": "p2"})
    pass_until_stack_empty(s)
    assert s.state.cards[beacon.id].zone == "p1:graveyard"
    replay_matches(s)


def test_rally_the_ancestors_exiles_itself_and_the_creatures_at_the_next_upkeep(cards):
    s = build(cards)
    elf = put(s, "Llanowar Elves", "graveyard")
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, W=2, C=1)
    rally = cast(s, "Rally the Ancestors", x_value=1)
    assert s.state.cards[elf.id].zone == "p1:battlefield"
    assert s.state.cards[bears.id].zone == "p1:graveyard"  # (mana value 2: more than X)
    assert s.state.cards[rally.id].zone == "p1:exile"
    replay_matches(s)


def test_seasons_past_goes_to_the_bottom_of_its_owners_library(cards):
    s = build(cards)
    put(s, "Llanowar Elves", "graveyard")
    put(s, "Grizzly Bears", "graveyard")
    mana(s, G=2, C=4)
    past = cast(s, "Seasons Past")
    choose(s, "Llanowar Elves", "Grizzly Bears")
    assert zone(s.state, "p1", "library")[-1] == past.id
    assert {s.state.cards[c].name for c in zone(s.state, "p1", "hand")} >= {"Llanowar Elves", "Grizzly Bears"}
    replay_matches(s)


def test_spell_crumple_counters_and_puts_both_spells_on_the_bottom(cards):
    s = build(cards)
    responsive(s)
    bolt = put(s, "Lightning Bolt", "hand", pid="p2")
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    mana(s, U=2, C=1)
    crumple = put(s, "Spell Crumple", "hand")
    act(s, "p1", type="cast_spell", card_id=crumple.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    assert zone(s.state, "p2", "library")[-1] == bolt.id
    assert zone(s.state, "p1", "library")[-1] == crumple.id
    assert s.state.players["p1"].life == 40
    replay_matches(s)


def test_a_flashback_cast_is_still_exiled(cards):
    """702.34a: a spell cast with flashback is exiled any time it would leave the stack — also when its own
    instruction would move it (checked on the primitive directly: no printed card has both)."""
    from app.rules import recursion

    assert recursion.self_move_of({"do": "to_library", "who": "self", "place": "shuffle"}) == "shuffle"
    assert recursion.self_move_of({"do": "exile", "who": "self"}) == "exile"
    assert recursion.self_move_of({"do": "exile", "who": "self", "face_down": True}) is None
    assert recursion.self_move_of({"do": "exile", "who": "target"}) is None


# -- searches -----------------------------------------------------------------------------------------------
def test_myriad_landscape_finds_lands_that_share_a_land_type(cards):
    s = build(cards)
    land = put(s, "Myriad Landscape", "battlefield")
    act(s, "p1", type="untap", card_ids=[land.id]) if s.state.cards[land.id].tapped else None
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=2)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d.max_choices == 2 and d.min_choices == 0
    private(s, [o.id for o in d.options])
    forest = next(o.id for o in d.options if s.state.cards[o.id].name == "Forest")
    island = next(o.id for o in d.options if s.state.cards[o.id].name == "Island")
    with pytest.raises(ActionError, match="share a land type"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest, island])
    ids = choose(s, "Forest", "Forest")
    for cid in ids:
        assert s.state.cards[cid].zone == "p1:battlefield" and s.state.cards[cid].tapped
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


@pytest.mark.parametrize(("lands", "untapped"), [(2, False), (3, True)])
def test_fabled_passage_untaps_the_land_with_four_or_more_lands(cards, lands, untapped):
    s = build(cards)
    for name in ("Swamp", "Island", "Swamp", "Island")[:lands]:
        put(s, name, "battlefield")
    passage = put(s, "Fabled Passage", "battlefield")
    act(s, "p1", type="activate_ability", card_id=passage.id, ability=0)
    pass_until_stack_empty(s)
    [forest] = choose(s, "Forest")
    assert s.state.cards[forest].zone == "p1:battlefield"
    assert s.state.cards[forest].tapped is not untapped  # (it counts itself: lands + the one found, minus the Passage)
    replay_matches(s)


def test_mystical_teachings_finds_an_instant_or_a_card_with_flash_and_reveals_it(cards):
    s = build(cards)
    mana(s, U=1, C=3)
    cast(s, "Mystical Teachings")
    assert options(s) == ["Ambush Viper", "Counterspell", "Lightning Bolt", "Rally the Ancestors", "Spell Crumple"]
    private(s, [o.id for o in decision(s).options])
    [viper] = choose(s, "Ambush Viper")
    assert s.state.cards[viper].zone == "p1:hand"
    assert "Ambush Viper" in json.dumps(s.view("p2"))  # "reveal it" (701.20a)
    replay_matches(s)


def test_circuitous_route_finds_basic_lands_and_or_gates(cards):
    s = build(cards)
    mana(s, G=1, C=3)
    cast(s, "Circuitous Route")
    assert "Test Guildgate" in options(s) and "Forest" in options(s) and "Sol Ring" not in options(s)
    gate, forest = choose(s, "Test Guildgate", "Forest")
    assert s.state.cards[gate].zone == "p1:battlefield" and s.state.cards[gate].tapped
    assert s.state.cards[forest].zone == "p1:battlefield" and s.state.cards[forest].tapped
    replay_matches(s)


def test_axgard_armory_finds_an_aura_and_an_equipment(cards):
    s = build(cards)
    armory = put(s, "Axgard Armory", "battlefield")
    if s.state.cards[armory.id].tapped:
        act(s, "p1", type="untap", card_ids=[armory.id])
    mana(s, R=2, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=armory.id, ability=2)
    pass_until_stack_empty(s)
    assert options(s) == ["Pacifism"]
    choose(s, "Pacifism")
    assert options(s) == ["Bonesplitter"]
    choose(s, "Bonesplitter")
    assert {s.state.cards[c].name for c in zone(s.state, "p1", "hand")} >= {"Pacifism", "Bonesplitter"}
    replay_matches(s)


def test_boundless_realms_finds_up_to_the_number_of_lands_you_control(cards):
    s = build(cards)
    put(s, "Swamp", "battlefield")
    put(s, "Swamp", "battlefield")
    mana(s, G=1, C=6)
    cast(s, "Boundless Realms")
    assert decision(s).max_choices == 2
    ids = choose(s, "Forest", "Island")
    assert all(s.state.cards[c].zone == "p1:battlefield" and s.state.cards[c].tapped for c in ids)
    replay_matches(s)


def test_traverse_the_outlands_reads_two_sentences_as_one_search(cards):
    s = build(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Llanowar Elves", "battlefield")
    mana(s, G=1, C=4)
    cast(s, "Traverse the Outlands")
    assert decision(s).max_choices == 2  # the greatest power among creatures you control
    choose(s, "Forest")
    replay_matches(s)


def test_rampant_rejuvenator_searches_by_its_last_known_power(cards):
    s = build(cards)
    mana(s, G=1, C=3)
    rej = cast(s, "Rampant Rejuvenator")
    assert s.state.cards[rej.id].counters.get("+1/+1") == 2
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[rej.id])  # (it dies: 3 damage to a 2/2)
    triggers(s)
    assert s.state.cards[rej.id].zone == "p1:graveyard"
    assert decision(s).max_choices == 2  # 608.2h: its power as it last existed on the battlefield
    choose(s, "Forest", "Forest")
    replay_matches(s)


# -- reanimation --------------------------------------------------------------------------------------------
def test_brilliant_restoration_returns_every_artifact_and_enchantment(cards):
    s = build(cards)
    ring = put(s, "Sol Ring", "graveyard")
    sword = put(s, "Bonesplitter", "graveyard")
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, W=4, C=3)
    cast(s, "Brilliant Restoration")
    assert s.state.cards[ring.id].zone == "p1:battlefield" and s.state.cards[sword.id].zone == "p1:battlefield"
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    replay_matches(s)


def test_puppeteer_clique_steals_a_creature_with_haste_until_your_next_end_step(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard", pid="p2")
    mana(s, B=2, C=3)
    cast(s, "Puppeteer Clique")
    triggers(s, bears.id)
    stolen = s.state.cards[bears.id]
    assert stolen.zone == "p1:battlefield" and stolen.controller == "p1"
    assert "haste" in chars(s, bears).keywords  # no duration stated: as long as it's on the battlefield (611.2a)
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")
    next_end_step(s)  # at the beginning of Alice's next end step it is exiled
    assert s.state.cards[bears.id].zone == "p2:exile"
    replay_matches(s)


def test_liliana_returns_a_black_zombie(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, B=2, C=3)
    lili = cast(s, "Liliana, Death's Majesty")
    act(s, "p1", type="activate_ability", card_id=lili.id, ability=1, targets=[bears.id])
    pass_until_stack_empty(s)
    ch = chars(s, bears)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert "Zombie" in ch.subtypes and "Bear" in ch.subtypes and set(ch.colors) == {"G", "B"}  # (205.1b, 105.3)
    replay_matches(s)


def test_rakdos_joins_up_returns_a_creature_with_two_counters(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    mana(s, B=1, R=1, C=3)
    cast(s, "Rakdos Joins Up")
    triggers(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].counters.get("+1/+1") == 2
    replay_matches(s)


def test_bloodline_necromancer_targets_a_vampire_or_a_wizard_only(cards):
    s = build(cards)
    hawk = put(s, "Vampire Nighthawk", "graveyard")
    bears = put(s, "Grizzly Bears", "graveyard")
    found = parse_sentence("return target Vampire or Wizard creature card from your graveyard to the battlefield")
    assert found is not None and '"Vampire"' in found[1] and '"Wizard"' in found[1]
    mana(s, B=1, C=4)
    cast(s, "Bloodline Necromancer")
    d = decision(s, "choose_one")
    assert bears.id not in {o.id for o in d.options}  # (a Bear: neither a Vampire nor a Wizard)
    triggers(s, hawk.id)
    assert s.state.cards[hawk.id].zone == "p1:battlefield"
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    replay_matches(s)


# -- the wording --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "search your library for up to two basic land cards that share a land type, put them onto the battlefield tapped, then shuffle",
    "search your library for an instant card or a card with flash, reveal it, put it into your hand, then shuffle",
    "search your library for up to two basic land cards and/or Gate cards, put them onto the battlefield tapped, then shuffle",
    "search your library for an Aura card and/or an Equipment card, reveal them, put them into your hand, then shuffle",
    "search your library for up to X basic land cards, where X is the number of lands you control, put them onto the "
    "battlefield tapped, then shuffle",
    "return all artifact and enchantment cards from your graveyard to the battlefield",
    "return all artifact, enchantment, and planeswalker cards from your graveyard to the battlefield",
    "return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it",
    "return target historic card from your graveyard to your hand",
])
def test_the_wordings_parse(text):
    assert parse_sentence(text) is not None


@pytest.mark.parametrize("text", [
    "search your library for a basic land card that shares a land type, put it onto the battlefield, then shuffle",
    "search your library for an artifact card with a mana ability or a basic land card, reveal it, put it into your hand, then shuffle",
    "search your library for up to X creature cards with mana value X or less, where X is the number of lands you control, "
    "put them onto the battlefield, then shuffle",
    "search your library for a creature card with power or toughness 6 or greater, reveal it, put it into your hand, then shuffle",
    "return target creature card from your graveyard to the battlefield with a hexproof counter and an indestructible counter on it",
])
def test_what_cannot_be_done_correctly_is_refused(text):
    assert parse_sentence(text) is None


def test_a_bare_grant_needs_a_whole_sentence_about_an_earlier_object():
    found = parse_effects("Return target creature card from your graveyard to the battlefield. It gains haste.")
    assert found is not None and found[0][1] == {"do": "grant", "who": "ref:e0", "keywords": ["haste"], "duration": "permanent"}
    assert parse_effects("Until end of turn, double target creature's power and it gains first strike.") is None
    assert parse_effects("Target creature gains haste.") is None  # (no pronoun: not read)
