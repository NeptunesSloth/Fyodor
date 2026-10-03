"""Scratch helper (wave 5H, not committed): dump counters-family lines."""
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from tools.commander_coverage import rows
from tools.gap_rank import _card, family_of

if __name__ == "__main__":
    fam = sys.argv[1] if len(sys.argv) > 1 else "counters"
    cards, _ = rows("/home/user/Fyodor/data/cards.sqlite")
    out = []
    with ProcessPoolExecutor(8) as pool:
        for r in pool.map(_card, cards, chunksize=256):
            if r is None:
                continue
            name, rank, level, _c, missing = r
            fams = [family_of(lab) if fid.startswith(("text:", "script:", "mana:")) else fid for fid, lab in missing]
            sole = len(set(fams)) == 1
            for (fid, lab), f in zip(missing, fams):
                if f == fam:
                    out.append((rank, name, sole, lab))
    out.sort()
    with open(f"/tmp/claude-0/-home-user-Fyodor/bb23a84f-4913-5b57-b95e-bffd10ab5ade/scratchpad/5h_{fam}.tsv", "w") as fh:
        for rank, name, sole, lab in out:
            fh.write(f"{rank}\t{name}\t{int(sole)}\t{lab}\n")
    print(len(out), Counter(s for _, _, s, _ in out))
    if len(sys.argv) > 2:
        pat = re.compile(sys.argv[2], re.I)
        hits = [(r, n, s, lab) for r, n, s, lab in out if pat.search(lab)]
        print("match", len(hits), "sole", sum(s for _, _, s, _ in hits))
        for r, n, s, lab in hits[: int(sys.argv[3]) if len(sys.argv) > 3 else 30]:
            print(r, n, s, "|", lab[:200])
