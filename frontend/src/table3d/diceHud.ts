/**
 * The landed dice's labels, as crisp DOM over the table (3D table or the 2D table's dice overlay): a chip over each
 * die with its number, readable from any seat, and a line by the roller saying what was rolled ("Bob · 2d6: 3 + 6 =
 * 9"). A d20's natural 20 is marked in gold, a natural 1 in ash red; a die the rules ignored has its chip struck
 * through and marked "ignored". Clicking a chip or the line clears those dice from this screen. Positions are fed
 * every frame by the renderer; elements are reused, so a resting roll costs a few style writes a frame.
 */
import "../game/dice.css";

/** A die's chip: `x, y` where the chip's bottom sits (over the die), `cy, r` the die's centre and size on screen. */
export interface HudChip { x: number; y: number; cy: number; r: number; visible: boolean; shown: boolean; label: string; ignored: boolean; crit: "high" | "low" | null }
export interface HudThrow {
  key: string;
  color: string;
  name: string;
  line: string;
  crit: "high" | "low" | null;
  /** The dice's centre on screen; the line goes below them (or above, when the roller is up the screen). */
  x: number;
  y: number;
  below: boolean;
  visible: boolean;
  shown: boolean;
  /** 0…1 as the dice are cleared away. */
  fade: number;
  chips: HudChip[];
}

interface Els { root: HTMLDivElement; line: HTMLButtonElement; chips: HTMLButtonElement[]; sig: string }

export class DiceHud {
  readonly el = document.createElement("div");
  private els = new Map<string, Els>();

  constructor(parent: HTMLElement, private onClear: (key: string) => void, fixed = false) {
    this.el.className = `dice-hud${fixed ? " fixed" : ""}`;
    this.el.setAttribute("aria-live", "polite");
    this.el.dataset.testid = "dice-hud";
    parent.append(this.el);
  }

  render(throws: HudThrow[]): void {
    const live = new Set<string>();
    for (const t of throws) {
      live.add(t.key);
      let e = this.els.get(t.key);
      const sig = `${t.line}|${t.chips.length}`;
      if (!e || e.sig !== sig) {
        e?.root.remove();
        e = this.build(t, sig);
        this.els.set(t.key, e);
      }
      const { root, line, chips } = e;
      root.style.opacity = String(t.fade);
      // chips: nudge apart where dice landed close together
      const placed: { x: number; y: number; h: number }[] = [];
      t.chips.forEach((c, i) => {
        const el = chips[i]!;
        const h = c.ignored ? 34 : 26;
        let { x, y } = c;
        for (let pass = 0; pass < 4; pass++) {
          const hit = placed.find((p) => Math.abs(p.x - x) < 32 && Math.abs(p.y - y) < Math.max(h, p.h));
          if (!hit) break;
          y = hit.y - hit.h - 2;
        }
        placed.push({ x, y, h });
        el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px) translate(-50%, -100%)`;
        el.classList.toggle("on", c.shown && c.visible);
      });
      // the line: below the dice, or above their chips
      const lineY = t.below
        ? Math.max(t.y, ...t.chips.map((c) => c.cy + c.r)) + 8
        : Math.min(t.y, ...placed.map((p) => p.y - p.h)) - 8;
      line.style.transform = `translate(${Math.round(t.x)}px, ${Math.round(lineY)}px) translate(-50%, ${t.below ? "0" : "-100%"})`;
      line.classList.toggle("on", t.shown && t.visible);
    }
    for (const [key, e] of this.els) {
      if (live.has(key)) continue;
      e.root.remove();
      this.els.delete(key);
    }
  }

  private build(t: HudThrow, sig: string): Els {
    const root = document.createElement("div");
    root.className = "dice-hud-throw";
    root.style.setProperty("--seat", t.color);
    root.dataset.testid = "dice-throw";
    const clear = () => this.onClear(t.key);
    const line = document.createElement("button");
    line.type = "button";
    line.className = `dice-line${t.crit ? ` crit-${t.crit}` : ""}`;
    line.title = "Clear these dice (from this screen)";
    line.setAttribute("aria-label", `${t.line}. Clear these dice`);
    line.dataset.testid = "dice-line";
    const text = document.createElement("span");
    text.className = "dice-line-text";
    text.textContent = t.line;
    line.append(text);
    if (t.crit) {
      const tag = document.createElement("span");
      tag.className = "dice-line-tag";
      tag.textContent = t.crit === "high" ? "Natural 20" : "Natural 1";
      line.append(tag);
    }
    const x = document.createElement("span");
    x.className = "dice-line-x";
    x.setAttribute("aria-hidden", "true");
    x.textContent = "×";
    line.append(x);
    line.addEventListener("click", clear);
    const chips = t.chips.map((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.tabIndex = -1; // the line is the keyboard target; chips repeat it for the pointer
      b.className = `dice-chip${c.ignored ? " ignored" : ""}${c.crit ? ` crit-${c.crit}` : ""}`;
      b.dataset.testid = "dice-chip";
      b.title = c.ignored ? "Ignored: the rules ignore this roll" : "Click to clear these dice";
      b.setAttribute("aria-label", c.ignored ? `${c.label}, ignored` : c.label);
      const n = document.createElement("span");
      n.className = "dice-chip-n";
      n.textContent = c.label;
      b.append(n);
      if (c.ignored) {
        const tag = document.createElement("span");
        tag.className = "dice-chip-tag";
        tag.textContent = "ignored";
        b.append(tag);
      }
      b.addEventListener("click", clear);
      root.append(b);
      return b;
    });
    root.append(line);
    this.el.append(root);
    return { root, line, chips, sig };
  }

  dispose(): void {
    this.el.remove();
    this.els.clear();
  }
}
