/**
 * The deck lab (deck editor → Stats): the curve, colour pips against land sources, the type breakdown, land-drop odds on the
 * play and the draw, and sample opening hands from a seed (deckLab.ts). Everything comes from the card cache on this screen.
 */
import { useMemo, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { ManaText } from "../cards/ManaText";
import { Modal } from "../components/Modal";
import type { CardData } from "../types/cards";
import type { DeckEntry } from "../types/decks";
import { curveStats, groupTitle } from "./deckBits";
import { COLORS, deckStats, keepRate, keeps, landDrops, libraryPool, sampleHand } from "./deckLab";

const pct = (p: number) => `${Math.round(p * 100)}%`;
const newSeed = () => Math.floor(Math.random() * 100000);

export function DeckStats({ entries, cards, onClose }: { entries: DeckEntry[]; cards: Record<string, CardData | undefined>; onClose: () => void }) {
  const s = useMemo(() => deckStats(entries, cards), [entries, cards]);
  const curve = useMemo(() => curveStats(entries, cards), [entries, cards]);
  const pool = useMemo(() => libraryPool(entries, cards), [entries, cards]);
  const N = s.library - s.missing;
  const drops = landDrops(N, s.lands);
  const maxCurve = Math.max(1, ...curve.buckets);
  const colors = COLORS.filter((c) => s.pips[c]); // (a colour the deck never pays: its "any colour" lands are noise)
  const totalPips = colors.reduce((n, c) => n + s.pips[c], 0);

  const [seed, setSeed] = useState(newSeed);
  const [hand, setHand] = useState<number | null>(null); // which hand of the seed is shown; mulligans = hand number
  const [rate, setRate] = useState<number | null>(null);
  const shown = hand === null ? [] : sampleHand(pool, seed, hand);
  const lands = shown.filter((c) => c.land).length;

  return (
    <Modal title="Deck stats" onClose={onClose} wide>
      <div className="ds-lab" data-testid="deck-stats">
        {s.missing > 0 && <p className="de-note">{s.missing} card{s.missing === 1 ? "" : "s"} not in the card data here {s.missing === 1 ? "is" : "are"} left out.</p>}
        <div className="ds-grid">
          <section className="ds-box" aria-labelledby="ds-curve">
            <h3 id="ds-curve">Mana curve <span className="de-panel-aside">{curve.average !== null ? `Average ${curve.average.toFixed(2)}` : ""}</span></h3>
            <div className="de-bars" role="img" aria-label={`Nonland cards by mana value: ${curve.buckets.map((n, i) => `${n} at ${i}${i === 7 ? " or more" : ""}`).join(", ")}`}>
              {curve.buckets.map((n, i) => (
                <div key={i} className={`de-bar ${n ? "" : "zero"}`}>
                  <span className="de-bar-n">{n || ""}</span>
                  <div className="de-bar-fill" style={{ "--h": n / maxCurve } as React.CSSProperties} />
                  <span className="de-bar-mv">{i === 7 ? "7+" : i}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="ds-box" aria-labelledby="ds-colors">
            <h3 id="ds-colors">Colours</h3>
            {colors.length === 0 ? <p className="de-note">No coloured costs.</p> : (
              <table className="ds-table">
                <thead><tr><th scope="col">Colour</th><th scope="col">Pips</th><th scope="col">Lands making it</th></tr></thead>
                <tbody>
                  {colors.map((c) => (
                    <tr key={c}>
                      <th scope="row"><ManaText text={`{${c}}`} /></th>
                      <td>{s.pips[c]} <span className="de-dim">{totalPips ? pct(s.pips[c] / totalPips) : ""}</span></td>
                      <td>{s.sources[c]} <span className="de-dim">of {s.lands}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="ds-box" aria-labelledby="ds-types">
            <h3 id="ds-types">Card types</h3>
            <dl className="ds-types">
              {s.types.map((t) => <div key={t.label}><dt>{groupTitle(t.label)}</dt><dd>{t.count}</dd></div>)}
            </dl>
          </section>

          <section className="ds-box" aria-labelledby="ds-lands">
            <h3 id="ds-lands">Land drops</h3>
            <p className="ds-lead">
              <b data-testid="ds-avg-lands">{N ? ((7 * s.lands) / N).toFixed(1) : "0"}</b> lands in an average opening seven
              <span className="de-dim"> ({s.lands} lands in {N} cards{s.mdfc ? `, ${s.mdfc} of them modal DFC land backs` : ""})</span>
            </p>
            <table className="ds-table">
              <thead><tr><th scope="col">Land drop by</th><th scope="col">On the play</th><th scope="col">On the draw</th></tr></thead>
              <tbody>
                {drops.map((d) => <tr key={d.turn}><th scope="row">Turn {d.turn}</th><td>{pct(d.play)}</td><td>{pct(d.draw)}</td></tr>)}
              </tbody>
            </table>
          </section>
        </div>

        <section className="ds-box ds-hands" aria-labelledby="ds-hands">
          <h3 id="ds-hands">Sample hands</h3>
          <div className="ds-hand-acts">
            <button className="tt-btn brass" disabled={!pool.length} onClick={() => { setSeed(newSeed()); setHand(0); setRate(null); }} data-testid="ds-draw">Draw sample hand</button>
            <button className="tt-btn" disabled={hand === null} onClick={() => setHand((h) => (h ?? 0) + 1)} data-testid="ds-mulligan">Mulligan</button>
            <button className="tt-btn" disabled={!pool.length} onClick={() => setRate(keepRate(pool, seed))} data-testid="ds-100">Draw 100 hands</button>
            <label className="ds-seed">Seed
              <input type="number" min={0} value={seed} onChange={(e) => { setSeed(Math.max(0, Math.floor(Number(e.target.value) || 0))); setHand((h) => (h === null ? null : 0)); setRate(null); }} />
            </label>
          </div>
          <p className="ds-lead" role="status" aria-live="polite">
            {hand !== null && <>{hand === 0 ? "Opening hand" : `Mulligan ${hand}${hand === 1 ? " (free in Commander)" : `: put ${hand - 1} on the bottom`}`}: {lands} land{lands === 1 ? "" : "s"}, {keeps(shown) ? "a keep" : "a mulligan"} by the 2–5 lands rule. </>}
            {rate !== null && <span data-testid="ds-keep-rate">Kept {rate} of 100 hands with 2–5 lands (seed {seed}).</span>}
          </p>
          {shown.length > 0 && (
            <ul className="ds-hand" aria-label="Sample hand">
              {shown.map((c, i) => <li key={i} title={c.name}>{cards[c.id] ? <CardFace card={cards[c.id]!} size="small" /> : c.name}</li>)}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
