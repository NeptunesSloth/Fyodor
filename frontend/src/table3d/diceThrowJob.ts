/**
 * A throw as a message (pure: no DOM, no WebGL; unit-tested): what the dice worker (diceThrow.worker.ts) is asked and
 * what it answers. The worker runs the very same throwRoll as the main thread would (same code, same seed, same
 * environment), so the tracks are the same bits; only the vectors and quaternions travel as plain numbers and each
 * track's frames as a transferred buffer. The server's numbers ride along unchanged: the worker only finds the
 * symmetry (`turn`) that shows them on top, as throwRoll always has.
 */
import * as THREE from "three";
import type { DiceShow } from "../game/dice";
import { cannonLaunch, launch, throwRoll, type Launcher, type ThrowEnv, type Thrown, type ThrownDie } from "./diceThrow";

type Show = Pick<DiceShow, "key" | "sides" | "results" | "coin" | "ignored">;
/** The launchers a job can name (a function can't be posted). */
export type LauncherName = "hand" | "cannon";
const LAUNCHERS: Record<LauncherName, Launcher> = { hand: launch, cannon: cannonLaunch };

/** A ThrowEnv with its hand as plain numbers. */
export interface EnvMsg extends Omit<ThrowEnv, "hand"> { hand: [number, number, number] }

export interface ThrowJob { id: number; show: Show; env: EnvMsg; launcher: LauncherName }

export interface DieMsg extends Omit<ThrownDie, "turn"> { turn: [number, number, number, number] }
export interface ThrowReply extends Omit<Thrown, "dice"> { id: number; dice: DieMsg[] }

/** Which name a launcher goes by (null: one the worker doesn't know; that throw stays on the main thread). */
export function launcherName(l: Launcher | undefined): LauncherName | null {
  if (!l || l === launch) return "hand";
  return l === cannonLaunch ? "cannon" : null;
}

export function toJob(id: number, show: Show, env: ThrowEnv, launcher: LauncherName): ThrowJob {
  const { key, sides, results, coin, ignored } = show;
  return {
    id,
    show: { key, sides, results: [...results], coin, ignored: ignored ? [...ignored] : undefined },
    env: { bounds: { ...env.bounds }, obstacles: env.obstacles.map((o) => ({ ...o })), hand: [env.hand.x, env.hand.y, env.hand.z], land: { ...env.land }, keep: { ...env.keep } },
    launcher,
  };
}

const envOf = (e: EnvMsg): ThrowEnv => ({ ...e, hand: new THREE.Vector3(...e.hand) });

/** The worker's side: throw it (exactly as throwRoll on the main thread) and pack the answer. */
export function runJob(job: ThrowJob): ThrowReply {
  const thrown = throwRoll(job.show, envOf(job.env), LAUNCHERS[job.launcher]);
  return {
    ...thrown,
    id: job.id,
    dice: thrown.dice.map((d) => ({ ...d, turn: [d.turn.x, d.turn.y, d.turn.z, d.turn.w] })),
  };
}

/** The buffers a reply hands over without copying (each track's frames). */
export function transferables(reply: ThrowReply): ArrayBuffer[] {
  return reply.dice.map((d) => d.track.frames.buffer as ArrayBuffer);
}

/** The main thread's side: the answer back as a Thrown. */
export function fromReply(reply: ThrowReply): Thrown {
  const { id: _id, dice, ...rest } = reply;
  return { ...rest, dice: dice.map((d) => ({ ...d, turn: new THREE.Quaternion(...d.turn) })) };
}
