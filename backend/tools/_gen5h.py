"""Scratch helper (wave 5H, not committed): card(...) fixture lines from the card DB."""
import json
import sqlite3
import sys

db = sqlite3.connect("file:/home/user/Fyodor/data/cards.sqlite?mode=ro", uri=True)
db.row_factory = sqlite3.Row
for i, name in enumerate(sys.argv[1:], 1):
    r = db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.name = ?", (name,)).fetchone()
    d = dict(r)
    kw = dict(set_code="tst", number=f"T5H{i}", mana_cost=d["mana_cost"] or "", cmc=float(d["cmc"] or 0), type_line=d["type_line"],
              oracle_text=d["oracle_text"] or "")
    if d.get("power") is not None:
        kw["power"], kw["toughness"] = d["power"], d["toughness"]
    if d.get("loyalty"):
        kw["loyalty"] = d["loyalty"]
    for k in ("colors", "color_identity", "keywords"):
        v = json.loads(d[k] or "[]")
        if v:
            kw[k] = v
    print(f"    card({name!r}, " + ", ".join(f"{k}={v!r}" for k, v in kw.items()) + "),")
