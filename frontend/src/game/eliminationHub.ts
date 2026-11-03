import type { GameView, MajorEvent, PracticeInfo } from "../types/game";
import { useGame } from "../state/gameStore";

/*
 * Major public events (docs/ELIMINATION_HUB.md, "Staying connected"): the server lists the newest few in every
 * view; each has an id and is announced once. A client never announces what was already true when it arrived
 * (a reconnect, a reload, coming back from the practice table), so nothing piles up or replays.
 */

/** Hands out each event once. The first look only notes what is already there. */
export class EventTracker {
  private seen: Set<string> | null = null;

  take(events: MajorEvent[] | undefined): MajorEvent[] {
    const list = events ?? [];
    if (!this.seen) {
      this.seen = new Set(list.map((e) => e.id));
      return [];
    }
    const fresh = list.filter((e) => !this.seen!.has(e.id));
    for (const e of fresh) this.seen.add(e.id);
    return fresh.slice(-MAX_BURST);
  }
}

/** At most this many notices from one update (a bigger burst keeps the newest). */
export const MAX_BURST = 3;

/**
 * What the live table announces: not the result (the result spotlight shows it to everyone) and not your own
 * departure (you get your own ELIMINATED moment).
 */
export function tableNotices(events: MajorEvent[], me: string | null): MajorEvent[] {
  return events.filter((e) => e.kind !== "result" && !(e.kind === "out" && me !== null && e.players.includes(me)));
}

/** Where "Return to live game" goes: the live table (as your seat, at a hot-seat table). */
export function liveHash(link: Pick<PracticeInfo, "of" | "seat" | "local">): string {
  return `#/game/${encodeURIComponent(link.of)}${link.local ? `?viewer=${encodeURIComponent(link.seat)}` : ""}`;
}

/** The live game is over or has moved on to another game: practice ends and the player goes back to the result. */
export function liveOver(link: Pick<PracticeInfo, "game">, live: GameView): boolean {
  const night = live.game.night;
  return !!night && (!!night.result || night.number !== link.game);
}

/** One line about the live game for the practice pill: whose turn, how many are left. */
export function liveLine(live: GameView): string {
  const r = live.rules;
  const left = live.seat_order.filter((pid) => {
    const p = live.players.find((x) => x.id === pid);
    return !p?.left && !(r && (r.conceded.includes(pid) || pid in r.lost));
  });
  const active = live.players.find((p) => p.id === live.turn.active_player)?.name;
  return [`Turn ${live.turn.number}`, active ? `${active}'s turn` : null, `${left.length} still in`].filter(Boolean).join(" · ");
}

/** The hub's Game log link: open the table's own log drawer (the public log and chat everyone at the table reads). */
export function openGameLog(): void {
  useGame.getState().setLayout({ logOpen: true });
}

const PRACTICE_KEY = (id: string) => `fyodor.practice.${id}`;

/** Remember which live game a practice table belongs to (for the way back, even if the table is gone). */
export function rememberPractice(id: string, link: PracticeInfo): void {
  try {
    sessionStorage.setItem(PRACTICE_KEY(id), JSON.stringify(link));
  } catch {
    /* the view carries it too */
  }
}

export function practiceLink(id: string): PracticeInfo | null {
  try {
    const raw = sessionStorage.getItem(PRACTICE_KEY(id));
    const link = raw ? (JSON.parse(raw) as PracticeInfo) : null;
    return link && typeof link.of === "string" && typeof link.seat === "string" ? link : null;
  } catch {
    return null;
  }
}

const SECTION_HEADER = /^(commanders?|deck|main(board)?|sideboard|maybeboard|tokens?|companions?|attractions|stickers):?$/i;

/** The commanders of a deck list in Fyodor's text format ("Commander" section, "1 Name (SET) 123" lines). */
export function commandersOf(text: string): string[] {
  const out: string[] = [];
  let inCommander = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (SECTION_HEADER.test(line)) {
      inCommander = /^commanders?:?$/i.test(line);
      continue;
    }
    if (!inCommander) continue;
    const name = line.replace(/^\d+\s*x?\s+/i, "").replace(/\s+\([A-Za-z0-9]+\)(\s+\S+)?$/, "").replace(/\s+\*[A-Z]+\*$/, "").trim();
    if (name) out.push(name);
  }
  return out;
}
