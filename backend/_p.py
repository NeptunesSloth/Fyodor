import sys, sqlite3, json
from app.rules import coverage, scripts, characteristics
db=sqlite3.connect('file:/home/user/Fyodor/data/cards.sqlite?mode=ro',uri=True); db.row_factory=sqlite3.Row
r=dict(db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id=p.id WHERE p.name='Grizzly Bears'").fetchone())
for k in ("colors","color_identity","keywords"): r[k]=json.loads(r[k] or "[]")
r['faces']=json.loads(r.pop('card_faces') or 'null') or []; r['legalities']=json.loads(r['legalities'] or '{}')
tl=sys.argv[1]
for t in sys.argv[2:]:
    d=dict(r); d['oracle_text']=t; d['id']=str(hash(t)); d['type_line']=tl; d['name']='Probe Card %d'%hash(t); d['power']='2'; d['toughness']='2'
    c=coverage.of_card_data(d)
    print(c.level, [f.label[:200] for f in c.features if not f.supported])
