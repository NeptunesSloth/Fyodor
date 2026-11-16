import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ManaText } from "../cards/ManaText";
import { imageUrl } from "../services/cards";
import { useCard } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import type { CardData } from "../types/cards";
import { SPECTATOR, type PlanarCardView, type PlanarFace, type PlanechaseView } from "../types/game";
import { send } from "./actions";
import { MOTION, motionMs, motionOn, onMotionSkip } from "./motion/timing";
import { isOut } from "./outOfGame";
import { FACE_LABEL, canRollPlanar, costText, onShowPlanarText, planarRollAction, planarRotation, planechaseCue, splitPlaneText } from "./planechase";
import "./planechase.css";

/*
 * -- planechase -- (CR 901, Commander's single shared planar deck) the plaque at the top right of both tables (it folds to one line): the face-up plane's
 * art (landscape) and name, its text on click, the planar die for the active player with what the next roll costs, and "Done —
 * planeswalk" on a phenomenon. The server deals, rolls and planeswalks (app/game/handlers/planechase.py); players apply what the
 * plane does by hand. With rules automation running the die's cost is charged from the roller's mana pool (the "tap your mana" prompt
 * when it's short: app/rules/planar_die.py); on a manual table it is shown and paid by hand. The plaque only knows the face-up card,
 * never the deck's order. On the 3D table (``compact``) the plane lies on the table itself (table3d/planar3d.ts): the plaque folds to
 * its name and die, and opens to the full card and text from its Text button or a click on the plane.
 *
 * Motion (docs/GAME_UI_MOTION_RESEARCH.md): a planeswalk slides the old plane off as the new one turns in; chaos pulses its symbol on
 * the plane and holds the chaos ability up until dismissed; the die tumbles onto its face. All at the player's animation speed
 * (motion/timing.ts), finished at once by any click or key, reduced to fades with reduced motion; the game never waits on them.
 */

const reduced = () => {
  if (usePrefs.getState().reducedMotion) return true;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

/** The planar die's faces, drawn (offline, no symbol font): the planeswalker symbol, the chaos symbol, a blank face. */
export function DieFace({ face }: { face: PlanarFace }) {
  if (face === "blank") return <svg viewBox="0 0 24 24" aria-hidden className="planar-glyph" />;
  if (face === "chaos") return <ChaosGlyph />;
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="planar-glyph">
      <path d="M12 2.5c1.4 3.2 1.9 6.6 1.6 10.4L12 21.5l-1.6-8.6C10.1 9.1 10.6 5.7 12 2.5z" fill="currentColor" />
      <path d="M5 6.5c2.6 1.3 4.4 3.4 5.2 6.4L9.4 17C7.6 13.8 6 10.4 5 6.5zM19 6.5c-2.6 1.3-4.4 3.4-5.2 6.4l.8 4.1c1.8-3.2 3.4-6.6 4.4-10.5z" fill="currentColor" />
    </svg>
  );
}

function ChaosGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="planar-glyph">
      <path d="M12 3a9 9 0 1 0 9 9" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M12 7.5a4.5 4.5 0 1 0 4.5 4.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M21 12l-2.6-3.4M16.5 12l-1.9-2.3" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" />
    </svg>
  );
}

/** A plane's text, its chaos ability set apart (and lit while chaos ensues). */
function PlaneText({ data, lit }: { data: CardData | undefined; lit: boolean }) {
  const { statics, chaos } = splitPlaneText(data?.oracle_text);
  if (!data) return <p className="planar-text dim">Reading the card…</p>;
  return (
    <div className="planar-text">
      {statics.map((l, i) => <p key={i}><ManaText text={l} /></p>)}
      {chaos && <p className={`planar-chaos-line ${lit ? "lit" : ""}`}><ChaosGlyph /><span><ManaText text={chaos} /></span></p>}
    </div>
  );
}

/**
 * The card's picture, landscape: an upright scan is turned a quarter (planarRotation, once it has loaded); with no picture (offline,
 * never downloaded), its name, type and text drawn on the plaque instead.
 */
function PlanarArt({ card, data, large }: { card: PlanarCardView; data: CardData | undefined; large?: boolean }) {
  const [rot, setRot] = useState<0 | 90 | null>(null); // null: not loaded yet (hidden, so an upright scan never flashes)
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="planar-art text-face">
        <b>{card.name}</b>
        <i>{data?.type_line ?? (card.phenomenon ? "Phenomenon" : "Plane")}</i>
        {large && <PlaneText data={data} lit={false} />}
      </div>
    );
  }
  return (
    <div className="planar-art">
      <img src={imageUrl(card.printing_id, 0, large ? "large" : "normal")} alt={card.name} draggable={false}
        className={rot === null ? "loading" : rot ? "turned" : ""}
        onLoad={(e) => setRot(planarRotation(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight))}
        onError={() => setFailed(true)} />
    </div>
  );
}

export function PlanechasePlaque({ me, compact = false }: { me: string; compact?: boolean }) {
  const view = useGame((s) => s.view);
  const pc = view?.planechase ?? null;
  const data = useCard(pc?.current.printing_id);
  const [open, setOpen] = useState(false);
  const [mini, setMini] = useState(false); // folded to one line: the name and the die
  const [chaosSeq, setChaosSeq] = useState<number | null>(null); // the chaos roll whose ability is held up
  const [leaving, setLeaving] = useState<{ card: PlanarCardView; id: number } | null>(null);
  const [cue, setCue] = useState<{ id: number; walk: boolean; chaos: boolean; rolled: boolean } | null>(null);
  const prev = useRef<PlanechaseView | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const art = useRef<HTMLButtonElement>(null);
  const away = useRef<HTMLDivElement>(null);
  const flash = useRef<HTMLSpanElement>(null);
  const die = useRef<HTMLSpanElement>(null);

  // -- 3D table -- a click on the plane lying on the table opens its text here
  useEffect(() => onShowPlanarText(() => {
    setOpen(true);
    setMini(false);
  }), []);

  // what changed since the last view: a planeswalk, a chaos roll, any roll (planechaseCue); nothing on first sight
  useEffect(() => {
    const before = prev.current;
    prev.current = pc;
    const c = planechaseCue(before, pc);
    if (!c || !pc) return;
    if (c.chaos) setChaosSeq(pc.last_roll?.seq ?? null);
    else if (c.walk || c.rolled) setChaosSeq(null); // (a new roll or plane: the old chaos is done)
    if (!motionOn()) return;
    const id = Date.now();
    if (c.walk && before) setLeaving({ card: before.current, id });
    setCue({ id, walk: c.walk, chaos: c.chaos, rolled: !!c.rolled });
  }, [pc]);

  // play the cue once the new plane is on the plaque (any click or key finishes it; the game never waits)
  useLayoutEffect(() => {
    if (!cue) return;
    const still = reduced();
    const anims: Animation[] = [];
    const go = (el: Element | null, frames: Keyframe[], ms: number, travel = true) => {
      if (!el || typeof (el as HTMLElement).animate !== "function") return;
      anims.push((el as HTMLElement).animate(frames, { duration: motionMs(ms, travel), easing: "cubic-bezier(0.23, 1, 0.32, 1)", fill: "both" }));
    };
    if (cue.rolled) go(die.current, still ? [{ opacity: 0 }, { opacity: 1 }] : [{ transform: "rotate(-220deg) scale(0.6)", opacity: 0 }, { transform: "none", opacity: 1 }], MOTION.lunge);
    if (cue.walk) {
      go(away.current, still ? [{ opacity: 1 }, { opacity: 0 }] : [{ transform: "none", opacity: 1 }, { transform: "translateX(-40%) rotate(-6deg)", opacity: 0 }], MOTION.cardTravel);
      go(art.current, still ? [{ opacity: 0 }, { opacity: 1 }] : [{ transform: "perspective(600px) rotateY(88deg)", opacity: 0.4 }, { transform: "none", opacity: 1 }], MOTION.cardTravel + 120);
    }
    if (cue.chaos) {
      go(flash.current, still ? [{ opacity: 0 }, { opacity: 0.9 }, { opacity: 0 }]
        : [{ opacity: 0, transform: "scale(0.5)" }, { opacity: 0.95, transform: "scale(1.1)", offset: 0.35 }, { opacity: 0, transform: "scale(1.35)" }], 700, false);
      go(stage.current, still ? [] : [{ transform: "none" }, { transform: "translateX(-2px)" }, { transform: "translateX(2px)" }, { transform: "none" }], 260);
    }
    const done = () => {
      setLeaving((l) => (l && l.id === cue.id ? null : l));
      for (const a of anims) a.cancel(); // (fill: both — let go of the end frame: the plaque's own style is the rest state)
    };
    if (anims.length) void Promise.all(anims.map((a) => a.finished)).then(done, () => undefined);
    else done();
    const off = onMotionSkip(() => anims.forEach((a) => a.finish()));
    return () => {
      off();
      for (const a of anims) a.finish(); // (the next cue, or the plaque leaving: this one is over)
    };
  }, [cue]);

  if (!view || !pc) return null;
  const seated = view.viewer !== SPECTATOR && view.players.some((p) => p.id === me) && !isOut(view, me);
  const mine = seated && canRollPlanar(view, me);
  const active = view.players.find((p) => p.id === view.turn.active_player);
  const roller = view.players.find((p) => p.id === pc.last_roll?.player);
  const phenomenon = pc.current.phenomenon;
  const chaos = chaosSeq !== null && pc.last_roll?.seq === chaosSeq ? splitPlaneText(data?.oracle_text).chaos : null;
  const auto = !!view.rules && !view.rules.paused; // (the die's cost is charged: planarRollAction)
  const roll = () => void send(planarRollAction(view));
  const walk = () => void send({ type: "planeswalk" });

  return (
    <section className={`planar-plaque ${open && !mini ? "open" : ""} ${mini ? "mini" : ""} ${compact ? "in-3d" : ""} ${phenomenon ? "is-phenomenon" : ""}`} aria-label="Planechase" data-testid="planar-plaque">
      <div className="planar-stage" ref={stage}>
        {leaving && <div className="planar-away" ref={away} aria-hidden><PlanarArt card={leaving.card} data={undefined} /></div>}
        <button type="button" className="planar-art-btn" ref={art} onClick={() => setOpen(!open)} aria-expanded={open}
          title={open ? "Hide the plane's text" : "Show the plane's text"} data-testid="planar-art">
          <PlanarArt key={pc.current.printing_id} card={pc.current} data={data} large={open} />
          <span className="planar-flash" ref={flash} aria-hidden><ChaosGlyph /></span>
        </button>
      </div>
      <div className="planar-info">
        <div className="planar-name" data-testid="planar-name">
          <span>{pc.current.name}</span>
          {phenomenon && <span className="planar-tag">Phenomenon</span>}
          {compact && !mini && <button type="button" className="planar-min planar-read" onClick={() => setOpen(!open)} aria-expanded={open}
            title={open ? "Hide the plane's text" : "Show the plane and its text (or click the plane on the table)"} data-testid="planar-read">Text</button>}
          <button type="button" className="planar-min" onClick={() => setMini(!mini)} aria-expanded={!mini}
            title={mini ? "Show the plane" : "Fold the plaque to one line"} aria-label={mini ? "Show the plane" : "Fold the plaque"}>{mini ? "+" : "–"}</button>
        </div>
        <div className="planar-sub">Planar deck {pc.count}{pc.visited_count ? ` · ${pc.visited_count} visited` : ""}</div>
        <div className="planar-die-row">
          {pc.last_roll && (
            <span className={`planar-die face-${pc.last_roll.face}`} ref={die} style={{ ["--seat" as string]: roller?.color }}
              title={`${roller?.name ?? "A player"} rolled ${FACE_LABEL[pc.last_roll.face].toLowerCase()}`} data-testid="planar-die">
              <DieFace face={pc.last_roll.face} />
            </span>
          )}
          {phenomenon ? (
            seated && <button type="button" className="tt-btn brass" onClick={walk} data-testid="planar-done"
              title="When everyone has applied the phenomenon: planeswalk to the next plane">Done — planeswalk</button>
          ) : mine ? (
            <button type="button" className="tt-btn brass" onClick={roll} data-testid="planar-roll"
              title={!pc.cost ? "Roll the planar die: free the first time this turn"
                : auto ? `Roll the planar die: costs ${costText(pc.cost)} this time, paid from your mana pool (tap your mana when asked)`
                : `Roll the planar die: costs ${costText(pc.cost)} this time (pay it from your pool)`}>
              Roll planar die <ManaText text={costText(pc.cost)} />
            </button>
          ) : (
            <span className="planar-wait">{active?.name ?? "The active player"} may roll · <ManaText text={costText(pc.cost)} /></span>
          )}
        </div>
      </div>
      <span className="sr-only" aria-live="polite">
        {pc.last_roll ? `${roller?.name ?? "A player"} rolled the planar die: ${pc.last_roll.face}. ` : ""}The table is on {pc.current.name}.
      </span>
      {open && !mini && (
        <div className="planar-detail" data-testid="planar-detail">
          {data?.type_line && <div className="planar-type">{data.type_line}</div>}
          <PlaneText data={data} lit={!!chaos} />
          {pc.visited.length > 0 && (
            <div className="planar-visited"><span>Visited</span> {pc.visited.slice(-6).map((c) => c.name).join(" · ")}</div>
          )}
          <div className="planar-tools">
            <span className="hint">{auto ? "Players apply the plane by hand; the die's cost is charged from your mana pool."
              : "Players apply the plane by hand; the die's cost is paid from your pool."}</span>
            {seated && !phenomenon && <button type="button" className="tt-btn ghost" onClick={walk} title="A card told the table to planeswalk">Planeswalk</button>}
          </div>
        </div>
      )}
      {chaos && (
        <div className="planar-chaos" role="status" data-testid="planar-chaos">
          <span className="planar-chaos-head"><ChaosGlyph /> Chaos ensues on {pc.current.name}</span>
          <p><ManaText text={chaos} /></p>
          <button type="button" className="tt-btn ghost" onClick={() => setChaosSeq(null)}>Done</button>
        </div>
      )}
    </section>
  );
}
