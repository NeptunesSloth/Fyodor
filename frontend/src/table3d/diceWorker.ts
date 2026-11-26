/**
 * Throws off the main thread: one dice worker (diceThrow.worker.ts), started with the dice and kept for the page. A throw
 * is posted to it and its tracks come back a moment later, simulated exactly as throwRoll would on the main thread
 * (diceThrowJob.ts). Until the worker has said it's ready (it loads cannon-es and three.js first), where there is no
 * Worker (tests, an old browser) or once it has failed, the throw is simulated here, at once, as before.
 */
import type { DiceShow } from "../game/dice";
import { throwRoll, type Launcher, type ThrowEnv, type Thrown } from "./diceThrow";
import { fromReply, launcherName, toJob, type ThrowReply } from "./diceThrowJob";

type Show = Pick<DiceShow, "key" | "sides" | "results" | "coin" | "ignored">;
interface Pending { show: Show; env: ThrowEnv; launcher: Launcher | undefined; done: (t: Thrown) => void }
type Message = ThrowReply | { id: number; error: string } | { ready: true };

let worker: Worker | null = null;
let ready = false;
let broken = false;
let nextId = 1;
const pending = new Map<number, Pending>();
/** A throw takes well under a second to simulate; one a live worker hasn't sent back by now is thrown here. */
const GIVE_UP_MS = 2500;

const supported = () => !broken && typeof Worker !== "undefined";

function failAll(): void {
  broken = true;
  ready = false;
  worker?.terminate();
  worker = null;
  // whatever was waiting is thrown here instead
  for (const [id, p] of pending) {
    pending.delete(id);
    p.done(throwRoll(p.show, p.env, p.launcher));
  }
}

function ensure(): Worker | null {
  if (worker || !supported()) return worker;
  try {
    worker = new Worker(new URL("./diceThrow.worker.ts", import.meta.url), { type: "module" });
  } catch {
    broken = true;
    return null;
  }
  worker.onmessage = (e: MessageEvent<Message>) => {
    const m = e.data;
    if ("ready" in m) {
      ready = true;
      return;
    }
    const p = pending.get(m.id);
    if (!p) return;
    pending.delete(m.id);
    p.done("error" in m ? throwRoll(p.show, p.env, p.launcher) : fromReply(m));
  };
  worker.onerror = () => failAll();
  return worker;
}

/** Start the worker ahead (it loads cannon-es and three.js once), so it's ready by the first throw. */
export function prewarmDiceWorker(): void {
  ensure();
}

/** Whether a throw can go to the worker now (it starts the worker if it isn't yet: the throws after this one go there). */
export function canThrowOffThread(): boolean {
  ensure();
  return ready && !!worker;
}

/**
 * Throw a roll on the worker; `done` gets the throw when it comes back. Returns false (and does nothing) when it can't go
 * there: no worker ready, or a launcher the worker doesn't know. The caller then throws it itself (throwRoll).
 */
export function throwOffThread(show: Show, env: ThrowEnv, launcher: Launcher | undefined, done: (t: Thrown) => void): boolean {
  const name = launcherName(launcher);
  if (!name || !canThrowOffThread()) return false;
  const w = worker!;
  const id = nextId++;
  pending.set(id, { show, env, launcher, done });
  // a worker that stops answering is given up on (this throw and any waiting are thrown here, and the rest stay here)
  setTimeout(() => {
    if (pending.has(id)) failAll();
  }, GIVE_UP_MS);
  try {
    w.postMessage(toJob(id, show, env, name));
  } catch {
    pending.delete(id);
    return false;
  }
  return true;
}
