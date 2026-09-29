"""Small synthetic Scryfall-shaped card set used by the test-suite."""

from __future__ import annotations

import uuid
from typing import Any

NS = uuid.UUID("7d3b0c1e-6a8e-4c79-9d7a-2f9a3b6d0e11")


def cid(key: str) -> str:
    return str(uuid.uuid5(NS, key))


def card(name: str, *, set_code: str = "tst", number: str = "1", **extra: Any) -> dict[str, Any]:
    key = f"{name}|{set_code}|{number}"
    base: dict[str, Any] = {
        "object": "card",
        "id": cid(key),
        "oracle_id": cid("oracle|" + name),
        "name": name,
        "lang": "en",
        "layout": "normal",
        "set": set_code,
        "set_name": set_code.upper() + " Set",
        "set_type": "expansion",
        "collector_number": number,
        "released_at": "2020-01-01",
        "rarity": "common",
        "mana_cost": "",
        "cmc": 0.0,
        "type_line": "Artifact",
        "oracle_text": "",
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "legalities": {"commander": "legal"},
        "digital": False,
        "promo": False,
        "border_color": "black",
        "image_uris": {"normal": f"https://img.example/{key}.jpg", "small": f"https://img.example/s/{key}.jpg"},
    }
    base.update(extra)
    return base


TREASURE = card("Treasure", set_code="ttst", number="T1", layout="token", set_type="token", type_line="Token Artifact — Treasure",
                oracle_text="{T}, Sacrifice this token: Add one mana of any color.")
GOBLIN = card("Goblin", set_code="ttst", number="T2", layout="token", set_type="token", type_line="Token Creature — Goblin",
              power="1", toughness="1", colors=["R"], color_identity=["R"])


def fixture_cards() -> list[dict[str, Any]]:
    return [
        card("Sol Ring", set_code="cmm", number="410", mana_cost="{1}", cmc=1.0, oracle_text="{T}: Add {C}{C}.", released_at="2023-08-04"),
        card("Sol Ring", set_code="c21", number="263", mana_cost="{1}", cmc=1.0, oracle_text="{T}: Add {C}{C}.", released_at="2021-04-23"),
        card("Sol Ring", set_code="sld", number="999", mana_cost="{1}", cmc=1.0, oracle_text="{T}: Add {C}{C}.",
             released_at="2024-01-01", set_type="box", promo=True),
        card("Arcane Signet", set_code="cmm", number="370", mana_cost="{2}", cmc=2.0, oracle_text="{T}: Add one mana of any color in your commander's color identity."),
        card("Command Tower", set_code="cmm", number="1000", type_line="Land", oracle_text="{T}: Add one mana of any color in your commander's color identity."),
        card("Island", set_code="cmm", number="1001", type_line="Basic Land — Island", oracle_text="({T}: Add {U}.)", color_identity=["U"]),
        card("Forest", set_code="cmm", number="1002", type_line="Basic Land — Forest", oracle_text="({T}: Add {G}.)", color_identity=["G"]),
        card("Mountain", set_code="cmm", number="1003", type_line="Basic Land — Mountain", oracle_text="({T}: Add {R}.)", color_identity=["R"]),
        card("Counterspell", set_code="cmm", number="81", mana_cost="{U}{U}", cmc=2.0, type_line="Instant", oracle_text="Counter target spell.",
             colors=["U"], color_identity=["U"]),
        card("Lightning Bolt", set_code="clb", number="187", mana_cost="{R}", cmc=1.0, type_line="Instant",
             oracle_text="Lightning Bolt deals 3 damage to any target.", colors=["R"], color_identity=["R"]),
        card("Llanowar Elves", set_code="dom", number="168", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf Druid",
             oracle_text="{T}: Add {G}.", power="1", toughness="1", colors=["G"], color_identity=["G"]),
        card("Krenko, Mob Boss", set_code="ddn", number="13", mana_cost="{2}{R}{R}", cmc=4.0, type_line="Legendary Creature — Goblin Warrior",
             oracle_text="{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
             power="3", toughness="3", colors=["R"], color_identity=["R"],
             all_parts=[{"object": "related_card", "id": GOBLIN["id"], "component": "token", "name": "Goblin", "type_line": "Token Creature — Goblin"}]),
        card("Atraxa, Praetors' Voice", set_code="2x2", number="190", mana_cost="{G}{W}{U}{B}", cmc=4.0,
             type_line="Legendary Creature — Phyrexian Angel Horror", oracle_text="Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
             power="4", toughness="4", colors=["W", "U", "B", "G"], color_identity=["W", "U", "B", "G"]),
        card("Delver of Secrets // Insectile Aberration", set_code="isd", number="51", layout="transform", mana_cost=None, cmc=1.0,
             type_line="Creature — Human Wizard // Creature — Human Insect", colors=["U"], color_identity=["U"], image_uris=None,
             card_faces=[
                 {"object": "card_face", "name": "Delver of Secrets", "mana_cost": "{U}", "type_line": "Creature — Human Wizard",
                  "oracle_text": "At the beginning of your upkeep, look at the top card of your library.", "power": "1", "toughness": "1",
                  "colors": ["U"], "image_uris": {"normal": "https://img.example/delver-front.jpg"}},
                 {"object": "card_face", "name": "Insectile Aberration", "mana_cost": "", "type_line": "Creature — Human Insect",
                  "oracle_text": "Flying", "power": "3", "toughness": "2", "colors": ["U"], "image_uris": {"normal": "https://img.example/delver-back.jpg"}},
             ]),
        card("Fire // Ice", set_code="mh2", number="290", layout="split", mana_cost="{1}{R} // {1}{U}", cmc=4.0,
             type_line="Instant // Instant", colors=["R", "U"], color_identity=["R", "U"],
             card_faces=[
                 {"object": "card_face", "name": "Fire", "mana_cost": "{1}{R}", "type_line": "Instant", "oracle_text": "Fire deals 2 damage divided as you choose."},
                 {"object": "card_face", "name": "Ice", "mana_cost": "{1}{U}", "type_line": "Instant", "oracle_text": "Tap target permanent.\nDraw a card."},
             ]),
        card("Bonecrusher Giant // Stomp", set_code="eld", number="115", layout="adventure", mana_cost="{2}{R} // {1}{R}", cmc=3.0,
             type_line="Creature — Giant // Instant — Adventure", colors=["R"], color_identity=["R"],
             card_faces=[
                 {"object": "card_face", "name": "Bonecrusher Giant", "mana_cost": "{2}{R}", "type_line": "Creature — Giant", "oracle_text": "Whenever...", "power": "4", "toughness": "3"},
                 {"object": "card_face", "name": "Stomp", "mana_cost": "{1}{R}", "type_line": "Instant — Adventure", "oracle_text": "Stomp deals 2 damage to any target."},
             ]),
        card("Lim-Dûl the Necromancer", set_code="tsp", number="114", mana_cost="{5}{B}{B}", cmc=7.0, type_line="Legendary Creature — Human Wizard",
             colors=["B"], color_identity=["B"], power="4", toughness="4"),
        card("Art Card", set_code="atst", number="A1", layout="art_series"),
        card("Swords to Plowshares", set_code="sta", number="10", mana_cost="{W}", cmc=1.0, type_line="Instant",
             oracle_text="Exile target creature. Its controller gains life equal to its power.", colors=["W"], color_identity=["W"]),
        card("Opt", set_code="eld", number="59", mana_cost="{U}", cmc=1.0, type_line="Instant",
             oracle_text="Scry 1.\nDraw a card.", colors=["U"], color_identity=["U"]),
        card("Pyroblast", set_code="ice", number="213", mana_cost="{R}", cmc=1.0, type_line="Instant",
             oracle_text="Choose one —\n• Counter target spell if it's blue.\n• Destroy target permanent if it's blue.",
             colors=["R"], color_identity=["R"], released_at="1995-06-01"),
        card("Seething Song", set_code="mir", number="193", mana_cost="{2}{R}", cmc=3.0, type_line="Instant",
             oracle_text="Add {R}{R}{R}{R}{R}.", colors=["R"], color_identity=["R"], released_at="1996-01-01"),
        card("Blazing Firesinger // Seething Song", set_code="sos", number="120", layout="prepare", cmc=3.0,
             type_line="Creature — Elf // Instant", colors=["R"], color_identity=["R"], released_at="2026-04-24",
             card_faces=[
                 {"object": "card_face", "name": "Blazing Firesinger", "mana_cost": "{2}{R}", "type_line": "Creature — Elf"},
                 {"object": "card_face", "name": "Seething Song", "mana_cost": "{2}{R}", "type_line": "Instant"},
             ]),
        TREASURE,
        GOBLIN,
        # --- M16 effect scenarios (current Oracle text) ---
        card("Elvish Visionary", set_code="tst", number="E1", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Elf Shaman",
             oracle_text="When this creature enters, draw a card.", power="1", toughness="1", colors=["G"], color_identity=["G"]),
        card("Thornwood Falls", set_code="tst", number="E2", type_line="Land",
             oracle_text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {U}.", color_identity=["G", "U"]),
        card("Murder", set_code="tst", number="E3", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Instant",
             oracle_text="Destroy target creature.", colors=["B"], color_identity=["B"]),
        card("Giant Growth", set_code="tst", number="E4", mana_cost="{G}", cmc=1.0, type_line="Instant",
             oracle_text="Target creature gets +3/+3 until end of turn.", colors=["G"], color_identity=["G"]),
        card("Perilous Myr", set_code="tst", number="E6", mana_cost="{2}", cmc=2.0, type_line="Artifact Creature — Phyrexian Myr",
             oracle_text="When this creature dies, it deals 2 damage to any target.", power="1", toughness="1"),
        card("Ambush Viper", set_code="tst", number="E7", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Snake",
             oracle_text="Flash\nDeathtouch", power="2", toughness="1", colors=["G"], color_identity=["G"], keywords=["Flash", "Deathtouch"]),
    ]
