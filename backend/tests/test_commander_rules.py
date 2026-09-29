"""Commander card rules (CR 903.3–903.5, 903.12e, 702.124): color identity, who can be a commander,
pairings, and the deck checks built on them. Cards are synthetic, shaped like card-DB rows."""

from __future__ import annotations

from app.decks.models import DeckEntry, DeckIn
from app.decks.service import validate
from app.rules import commander as C


def card(name, type_line, *, cost="", text="", colors=None, faces=None, power=None, toughness=None, legal="legal", layout="normal"):
    return {"name": name, "type_line": type_line, "mana_cost": cost, "oracle_text": text, "colors": colors or [],
            "faces": faces or [], "power": power, "toughness": toughness, "legalities": {"commander": legal},
            "layout": layout}


def test_color_identity_follows_903_4():
    bosh = card("Bosh, Iron Golem", "Legendary Artifact Creature — Golem", cost="{8}",
                text="{3}{R}, Sacrifice an artifact: Bosh, Iron Golem deals damage equal to the sacrificed artifact's mana value to any target.")
    assert C.color_identity(bosh) == ("R",)  # the CR's own example
    assert C.color_identity(card("Wort", "Legendary Creature — Goblin", cost="{4}{R/G}{R/G}")) == ("R", "G")
    assert C.color_identity(card("Mite", "Artifact Creature", cost="{W/P}")) == ("W",)
    assert C.color_identity(card("Twobrid", "Instant", cost="{2/U}")) == ("U",)
    assert C.color_identity(card("Reminder", "Creature", cost="{1}", text="Kicker {2} (You may pay an additional {R} as you cast this spell.)")) == ()
    scholar = card("Civilized Scholar // Homicidal Brute", "Creature — Human Advisor // Creature — Human Mutant", layout="transform",
                   faces=[{"name": "Civilized Scholar", "mana_cost": "{2}{U}", "colors": ["U"], "oracle_text": ""},
                          {"name": "Homicidal Brute", "mana_cost": "", "colors": ["R"], "oracle_text": ""}])
    assert C.color_identity(scholar) == ("U", "R")  # the back face's color indicator counts (903.4d)
    assert C.color_identity(card("Courier", "Artifact Creature", cost="{3}", text="Courier is all colors.")) == ("W", "U", "B", "R", "G")
    wayfarer = card("Fallaji Wayfarer", "Creature — Human Scout", cost="{2}{G}", colors=["W", "U", "B", "R", "G"],
                    text="Fallaji Wayfarer is all colors. This ability doesn't affect its color identity.")
    assert C.color_identity(wayfarer) == ("G",)
    assert C.color_identity(card("Rograkh", "Legendary Creature — Kobold", cost="{0}", colors=["R"])) == ("R",)  # indicator
    assert C.color_identity(card("Tundra", "Land — Plains Island", text="({T}: Add {W} or {U}.)")) == ()  # see 903.5d
    assert C.basic_land_mana(card("Tundra", "Land — Plains Island")) == {"W", "U"}


def test_who_can_be_a_commander_903_3():
    assert C.can_be_commander(card("Krenko", "Legendary Creature — Goblin Warrior"))
    assert C.can_be_commander(card("Skysovereign", "Legendary Artifact — Vehicle"))
    assert C.can_be_commander(card("Ship", "Legendary Artifact — Spacecraft", power="4", toughness="4"))
    assert not C.can_be_commander(card("Station", "Legendary Artifact — Spacecraft"))  # no P/T box
    assert not C.can_be_commander(card("Grizzly Bears", "Creature — Bear"))
    assert not C.can_be_commander(card("Urza's Saga", "Legendary Enchantment Land — Urza's Saga"))
    assert C.can_be_commander(card("Teferi", "Legendary Planeswalker — Teferi", text="Teferi, Temporal Archmage can be your commander."))
    assert C.can_be_commander(card("Candlekeep Sage", "Legendary Enchantment — Background"))  # (only with a partner)


def test_partner_abilities_702_124():
    p1 = card("Thrasios", "Legendary Creature — Merfolk", text="Partner")
    p2 = card("Tymna", "Legendary Creature — Human", text="Partner")
    f1 = card("Sophina", "Legendary Creature — Dwarf", text="Menace\nPartner—Friends forever")
    f2 = card("Othelm", "Legendary Creature — Human", text="Partner—Friends forever")
    s1 = card("Ellie", "Legendary Creature — Human", text="Partner—Survivors")
    w1 = card("Lore Weaver", "Legendary Creature — Human", text="Partner with Ley Weaver")
    w2 = card("Ley Weaver", "Legendary Creature — Human", text="Partner with Lore Weaver (When this creature enters, …)")
    bg = card("Wilson", "Legendary Creature — Bear", text="Choose a Background")
    back = card("Candlekeep Sage", "Legendary Enchantment — Background")
    doc = card("Donna", "Legendary Creature — Human", text="Doctor’s companion")
    tardis_doc = card("The Tenth Doctor", "Legendary Creature — Time Lord Doctor")
    assert C.pair_problem(p1, p2) is None and C.pair_problem(f1, f2) is None
    assert C.pair_problem(w1, w2) is None and C.pair_problem(bg, back) is None and C.pair_problem(doc, tardis_doc) is None
    assert C.pair_problem(f1, s1) is not None  # different partner—[text] abilities
    assert C.pair_problem(p1, f1) is not None  # partner and partner—[text] can't combine (702.124f)
    assert C.pair_problem(w1, p1) is not None
    assert "no partner ability" in C.pair_problem(card("A", "Legendary Creature"), card("B", "Legendary Creature"))
    assert C.configuration_problems([back]) == ["Candlekeep Sage is a Background: it needs a commander with “Choose a Background”"]
    assert C.configuration_problems([p1, p2]) == []
    assert len(C.configuration_problems([p1, p2, f1])) >= 1
    assert C.deck_identity([card("W", "Legendary Creature", cost="{W}"), card("U", "Legendary Creature", cost="{U}")]) == ("W", "U")


def _deck(commanders, others):
    data = {}
    entries = []
    for i, (section, c) in enumerate([*(("commander", c) for c in commanders), *(("main", c) for c in others)]):
        pid = f"p{i}"
        data[pid] = c
        entries.append(DeckEntry(section=section, quantity=1, name=c["name"], printing_id=pid))
    return DeckIn(name="t", format="commander", entries=entries), data


def messages(commanders, others):
    deck, data = _deck(commanders, others)
    return [w.message for w in validate(deck, None, data)]  # type: ignore[arg-type]


def test_deck_checks_use_the_same_identity():
    wort = card("Wort", "Legendary Creature — Goblin", cost="{4}{R/G}{R/G}")
    msgs = messages([wort], [card("Counterspell", "Instant", cost="{U}{U}"),
                             card("Tundra", "Land — Plains Island", text="({T}: Add {W} or {U}.)"),
                             card("Taiga", "Land — Mountain Forest", text="({T}: Add {R} or {G}.)"),
                             card("Banned Card", "Artifact", cost="{1}", legal="banned"),
                             card("Silver Border", "Artifact", cost="{1}", legal="not_legal")])
    assert any("Counterspell is outside the commander's color identity (U)" in m for m in msgs)
    assert any("Tundra has a basic land type producing WU" in m for m in msgs)  # 903.5d
    assert not any("Taiga" in m for m in msgs)
    assert any("Banned Card is on the Commander banned list" in m for m in msgs)
    assert any("Silver Border isn't legal in Commander" in m for m in msgs)
    bears = card("Grizzly Bears", "Creature — Bear", cost="{1}{G}")
    assert any("can't be a commander" in m for m in messages([bears], []))


def test_colorless_commander_may_use_basics_of_one_type():
    kozilek = card("Kozilek", "Legendary Creature — Eldrazi", cost="{10}")
    wastes_ok = messages([kozilek], [card("Island", "Basic Land — Island"), card("Island", "Basic Land — Island")])
    assert not any("basic land" in m.lower() and "one basic land type" in m for m in wastes_ok)
    mixed = messages([kozilek], [card("Island", "Basic Land — Island"), card("Swamp", "Basic Land — Swamp")])
    assert any("only one basic land type" in m for m in mixed)  # 903.12e


def test_commander_coverage_reports_only_count_commander_legal_cards(card_db, tmp_path):
    import json

    from tools import commander_coverage

    assert commander_coverage.main(["--db", str(card_db), "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "commander_rules_coverage.json").read_text())
    assert data["commander_legal_cards"] > 0 and sum(data["levels"].values()) == data["commander_legal_cards"]
    names = {row["name"] for row in data["commanders"]}
    assert "Krenko, Mob Boss" in names and "Sol Ring" not in names  # legal, but not a commander
    md = (tmp_path / "commander_rules_coverage.md").read_text()
    assert "Commander-legal cards" in md and "Top Commander features to implement next" in md
    assert (tmp_path / "commander_coverage.md").read_text().startswith("# Commander coverage")
    assert (tmp_path / "mechanics.md").exists()


def test_banned_cards_are_left_out_of_the_pool():
    from app.rules import pool

    rep = pool.analyse([card("Banned", "Artifact", cost="{1}", legal="banned") | {"oracle_id": "b"},
                        card("Other Format", "Artifact", cost="{1}", legal="not_legal") | {"oracle_id": "o"},
                        card("Bear", "Creature — Bear", cost="{1}{G}", power="2", toughness="2") | {"oracle_id": "g"}])
    assert (rep.total, rep.banned, rep.levels["FULL"]) == (1, 1, 1)  # a vanilla creature is FULL


def test_partner_family_is_deckbuilding_only_702_124a():
    """Partner abilities function before the game begins (702.124a): nothing to automate in play,
    except "Partner with [name]", which also has an enters trigger (702.124j)."""
    from app.rules import coverage
    from app.rules.characteristics import printed_from_data

    def level(name, text):
        data = card(name, "Legendary Creature — Test", cost="{1}", text=text, power="1", toughness="1") | {"id": name}
        return coverage.of_characteristics(printed_from_data(data)).level

    assert level("Pal", "Partner") == "FULL"
    assert level("Friend", "Partner—Friends forever") == "FULL"
    assert level("Hero", "Choose a Background") == "FULL"
    assert level("Companion", "Doctor's companion") == "FULL"
    assert level("Walker", "Walker can be your commander.") == "FULL"  # 903.3a
    assert level("Twin", "Partner with Other Twin") == "PARTIAL"
