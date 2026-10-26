# ruff: noqa: F811  (the imported fixtures are used as test arguments)
"""Wave 110I session 11: Wee Champion and Goblin Airbrusher (123.2 stickers, 608.2c "instead"): a sticker of any kind placed on any card by you triggers them; an
art sticker gives the other mode."""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import find, put
from tests.test_rules_sticker_effects101 import DATA, FixedSheetRng, cast, pick, place, question
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check
from tests.wave100c_kit import to_phase

WEE = "Whenever you place a sticker, this creature gets +1/+1 until end of turn. If it's an art sticker, instead put a +1/+1 counter on this creature."
AIR = ("Whenever you place a sticker, create a Treasure token. If it's an art sticker, instead create two Treasure tokens. "
       "(They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")")
BALLS = ("When this enchantment enters, you may put a name sticker on it.\nWhenever you put a sticker on this enchantment, it deals damage equal to the number of o's "
         "in name stickers on this enchantment to any target.")
SPLASH = ("Flash\nWhen this enchantment enters, you may put a name sticker on it.\nWhenever you put a sticker on this enchantment, tap up to X target creatures, where X is the "
          "number of u's in name stickers on this enchantment.")
WOLF = ("When this creature enters, you may put a name sticker on it. When you do, up to X target creatures each get -1/-1 until end of turn, where X is the number "
        "of unique vowels on that sticker. (The vowels are A, E, I, O, U, and Y.)")
PIN = ("When this Equipment enters, you may put an ability sticker with ticket cost X or less on it without paying that sticker's ticket cost.\n"
       "Equipped creature gets +1/+1 and has all abilities of ability stickers on this Equipment.\nEquip {2}")
BOSS = ("Other Riggers you control get +1/+0 and have haste.\nIf a Rigger you control would assemble a Contraption, it assembles two Contraptions instead.")
EXTRA = [real("Steamflogger Boss", "{2}{R}", 3, "Creature \u2014 Goblin Rigger", BOSS, ("2", "2"), "R"), real("Rigger Probe", "{R}", 1, "Creature \u2014 Goblin Rigger", "", ("1", "1"), "R"),
         real("Pin Collection", "{X}{W}", 1, "Artifact \u2014 Equipment", PIN), real("Wolf in _____ Clothing", "{2}{G}", 3, "Creature \u2014 Wolf", WOLF, ("2", "2"), "G"), real("_____ Balls of Fire", "{1}{R}", 2, "Enchantment", BALLS, None, "R"), real("Make a _____ Splash", "{1}{U}", 2, "Enchantment", SPLASH, None, "U"),
         real("Wee Champion", "{1}{R}", 2, "Creature — Goblin Warrior", WEE, ("2", "2"), "R"),
         real("Goblin Airbrusher", "{1}{R}", 2, "Creature — Goblin Artificer", AIR, ("2", "2"), "R")]


@pytest.fixture()
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        fields = {k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")}
        rows[c["name"]] = card(c["name"], set_code=c.get("set_code", "sf101") if "Attraction" in c.get("type_line", "") else "sf101",
                               number=str(c.get("collector_number", i)) if "Attraction" in c.get("type_line", "") else str(i), **fields)
    for c in EXTRA:
        rows[c["name"]] = c
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def start(cards):
    names = ["Grizzly Bears", "Ticketomaton", "Wee Champion", "Goblin Airbrusher", "_____ Balls of Fire", "Make a _____ Splash", "Wolf in _____ Clothing", "Pin Collection", "Steamflogger Boss", "Rigger Probe"]
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in names)])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


@pytest.mark.parametrize("name", ["Wee Champion", "Goblin Airbrusher", "_____ Balls of Fire", "Make a _____ Splash", "Wolf in _____ Clothing", "Pin Collection", "Steamflogger Boss"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("kind", ["art", "name"])
def test_wee_champion_and_goblin_airbrusher(cards, kind):
    """Ticketomaton's sticker goes on a Bear (a non-Champion): art, Wee gets a +1/+1 counter and Airbrusher makes two Treasures; otherwise Wee gets +1/+1 until end of turn and
    Airbrusher makes one."""
    s = start(cards)
    put(s, "Goblin Airbrusher", "battlefield")
    wee, bear = put(s, "Wee Champion", "battlefield"), put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ticketomaton")
    place(s, bear.id, kind=kind)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [o.id for o in d.options][: max(1, d.min_choices)])
    w = s.state.cards[wee.id]
    treasures = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Treasure"]
    assert (w.counters.get("+1/+1", 0), len(treasures)) == ((1, 2) if kind == "art" else (0, 1))
    oid = s.state.rules.object_id(wee.id)
    assert any(oid in e.affected and e.power == 1 for e in s.state.rules.effects) == (kind != "art")  # (+1/+1 until end of turn only for a non-art sticker)
    check(s)


def _settle(s, first=True):
    for _ in range(14):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [o.id for o in d.options][: max(1, d.min_choices)] if not first else [d.options[0].id])


def _best(s, letter):
    """The available name sticker with the most of ``letter`` (and how many)."""
    from app.rules import stickers101
    from app.rules.plan import Plan

    texts = [v["text"] for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", "name")]
    best = max(texts, key=lambda x: x.casefold().count(letter))
    return best, best.casefold().count(letter)


def test_balls_of_fire(cards):
    """123.2: the sticker put on it as it enters triggers it: damage equals the o's in its name stickers ("Cannonball": 2); a Ticketomaton sticker elsewhere does not."""
    s = start(cards)
    cast(s, "_____ Balls of Fire")
    balls = find(s, "_____ Balls of Fire")
    text, n = _best(s, "o")
    assert n >= 1
    place(s, balls.id, kind="name", text=text)
    d = question(s)
    pick(s, ["p2"] if "p2" in [o.id for o in d.options] else [d.options[0].id])
    _settle(s)
    assert s.state.players["p2"].life == 40 - n
    check(s)


def test_make_a_splash(cards):
    """123.2: tap up to X target creatures, X the u's in its name stickers ("Circus": 1)."""
    s = start(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Make a _____ Splash")
    splash = find(s, "Make a _____ Splash")
    text, n = _best(s, "u")
    assert n >= 1
    place(s, splash.id, kind="name", text=text)
    d = question(s)
    pick(s, [bear.id] if bear.id in [o.id for o in d.options] else [d.options[0].id])
    _settle(s)
    assert s.state.cards[bear.id].tapped
    check(s)


def test_wolf_in_clothing(cards):
    """603.12: the reflexive trigger follows a name sticker put on it; X is that sticker's unique vowels (a, e, i, o, u, y): up to X creatures get -1/-1 until end of turn."""
    s = start(cards)
    bears = [put(s, "Grizzly Bears", "battlefield")]
    cast(s, "Wolf in _____ Clothing")
    wolf = find(s, "Wolf in _____ Clothing")
    from app.rules import stickers101
    from app.rules.plan import Plan

    texts = [v["text"] for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", "name")]
    text = max(texts, key=lambda x: len(set(x.casefold()) & set("aeiouy")))
    place(s, wolf.id, kind="name", text=text)
    d = question(s)
    assert d.max_choices == min(len(set(text.casefold()) & set("aeiouy")), 2)  # (only the Bears and the Wolf are creatures)
    pick(s, [bears[0].id])
    _settle(s)
    oid = s.state.rules.object_id(bears[0].id)
    assert any(oid in e.affected and e.power == -1 and e.toughness == -1 for e in s.state.rules.effects)
    check(s)


def test_pin_collection(cards):
    """123.2, 107.3m: cast with X=2 it offers only ability stickers of ticket cost 2 or less (placed free: no tickets spent); the equipped creature has the sticker's ability
    and +1/+1, and loses it when unequipped (613.1f)."""
    from app.rules.plan import Plan

    s = start(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Pin Collection", x_value=2)
    pin = find(s, "Pin Collection")
    d = question(s)
    pick(s, [pin.id])
    offered = [o.id for o in s.state.rules.decision.options]
    from app.rules import stickers101

    mine = {v["id"]: v for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", "ability")}
    assert offered and all(mine[i]["cost"] <= 2 for i in offered if i in mine) and any(v["cost"] > 2 for v in mine.values())
    chosen = next(mine[i] for i in offered if mine[i]["text"] == "Deathtouch")
    pick(s, [chosen["id"]])
    _settle(s, first=False)
    assert d is not None and s.state.players["p1"].resources.get("ticket", 0) == 0
    equip = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(pin).abilities if "equip" in a.keywords)
    act(s, "p1", type="activate_ability", card_id=pin.id, ability=equip, targets=[bear.id], sources=[])
    _settle(s, first=False)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[pin.id].attached_to == bear.id
    assert "deathtouch" in Plan(s.state, "p1", s.cards, None).ch(bear).keywords
    act(s, "p1", type="attach", card_ids=[pin.id], to="p2")  # (off the Bear: by hand)
    assert "deathtouch" not in Plan(s.state, "p1", s.cards, None).ch(bear).keywords
    check(s)


def test_steamflogger_boss(cards):
    """613.4c, 701.45a: other Riggers you control get +1/+0 and haste (the Boss itself and a Bear do not); assembling is outside these rules and no Contraption deck exists in a
    Commander game, so its replacement never applies."""
    from app.rules.plan import Plan

    s = start(cards)
    boss, rigger, bear = (put(s, n, "battlefield") for n in ("Steamflogger Boss", "Rigger Probe", "Grizzly Bears"))
    ch = {c.name: Plan(s.state, "p1", s.cards, None).ch(c) for c in (boss, rigger, bear)}
    assert ("haste" in ch["Rigger Probe"].keywords, "haste" in ch["Steamflogger Boss"].keywords, "haste" in ch["Grizzly Bears"].keywords) == (True, False, False)
    assert (ch["Rigger Probe"].pt, ch["Steamflogger Boss"].pt, ch["Grizzly Bears"].pt) == ((2, 1), (2, 2), (2, 2))
    check(s)
