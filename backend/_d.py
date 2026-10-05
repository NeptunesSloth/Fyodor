import sys, sqlite3, json
from pathlib import Path
from app.rules import coverage
from tools.commander_coverage import rows
rs,_=rows(Path('/home/user/Fyodor/data/cards.sqlite'))
want=set(sys.argv[1:])
for d in rs:
    if d['name'] in want or (not want):
        c=coverage.of_card_data(d)
        print(d['name'],c.level)
        for f in c.features:
            if not f.supported: print('   X',f.label[:300])
