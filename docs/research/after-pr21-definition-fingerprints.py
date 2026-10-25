from __future__ import annotations
import argparse,dataclasses,gzip,hashlib,json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from app.rules import commander,scripts
from tools.inventory import _faces
from tools.commander_coverage import rows

def encode(v):
 if isinstance(v,(set,frozenset)):return sorted(v)
 if dataclasses.is_dataclass(v):return dataclasses.asdict(v)
 if hasattr(v,'model_dump'):return v.model_dump(mode='json')
 raise TypeError(type(v).__name__)
def one(data):
 if commander.legality(data)!='legal':return None
 payload=[scripts.definitions(ch) for ch in _faces(data)]
 raw=json.dumps(payload,sort_keys=True,separators=(',',':'),default=encode).encode()
 return data['name'],hashlib.sha256(raw).hexdigest()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 data,meta=rows(Path('/workspace/Fyodor/data/cards.sqlite'))
 with ProcessPoolExecutor(2) as pool: hashes=dict(x for x in pool.map(one,data,chunksize=256) if x is not None)
 a.out.write_bytes(gzip.compress(json.dumps({'meta':meta,'hash_algorithm':'definition-json-v1','hashes':hashes},sort_keys=True).encode(),mtime=0))
 print('definition fingerprints',len(hashes))
