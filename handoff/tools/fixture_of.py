"""fixture_of.py NAME... -> JSON list of fixture dicts (name, layout, mana_cost, cmc, type_line, oracle_text, colors, color_identity, keywords, power, toughness, card_faces)"""
import json, sqlite3, sys
db = sqlite3.connect("file:../data/cards.sqlite?mode=ro", uri=True); db.row_factory = sqlite3.Row
out = []
for name in sys.argv[1:]:
    r = db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.name = ? AND p.is_token = 0", (name,)).fetchone()
    if r is None:
        print("MISSING", name, file=sys.stderr); continue
    d = dict(r)
    c = {"name": d["name"], "layout": d["layout"], "mana_cost": d["mana_cost"] or "", "cmc": d["cmc"], "type_line": d["type_line"],
         "oracle_text": d["oracle_text"] or "", "colors": json.loads(d["colors"] or "[]"), "color_identity": json.loads(d["color_identity"] or "[]"),
         "keywords": json.loads(d["keywords"] or "[]")}
    for k in ("power", "toughness", "loyalty"):
        if d.get(k) is not None: c[k] = d[k]
    faces = json.loads(d["card_faces"] or "null")
    if faces: c["card_faces"] = faces
    out.append(c)
print(json.dumps(out, ensure_ascii=False, indent=1))
