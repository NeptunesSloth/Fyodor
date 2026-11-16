/**
 * The dice worker: simulates a throw (diceThrowJob.ts runJob: cannon-es, a few hundred steps per die) off the main thread,
 * so a big handful doesn't stall a frame. It only computes the tracks; the three.js loop plays them back (dice.ts).
 */
import { runJob, transferables, type ThrowJob } from "./diceThrowJob";

const scope = self as unknown as { onmessage: ((e: MessageEvent<ThrowJob>) => void) | null; postMessage(msg: unknown, transfer?: Transferable[]): void };

scope.onmessage = (e) => {
  try {
    const reply = runJob(e.data);
    scope.postMessage(reply, transferables(reply));
  } catch (err) {
    // the main thread throws it itself instead (diceWorker.ts)
    scope.postMessage({ id: e.data.id, error: String(err) });
  }
};
// loaded (cannon-es, three.js and the solids' code): throws can come here now (diceWorker.ts)
scope.postMessage({ ready: true });
