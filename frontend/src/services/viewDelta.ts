/**
 * -- view deltas -- the server's patches (backend/app/multiplayer/view_delta.py): after the first full view, each update names the view
 * it applies to (`base`: the number of the last view message sent on this connection) and what changed from it. Applying one gives exactly
 * the view the server built for this viewer; anything that does not fit (another base, a key or list that isn't there) throws, and the
 * connection asks for the whole view again (`GameConnection.resync`).
 *
 * The base is never changed: the result shares every unchanged part with it (a card nobody touched is the same object as before), so the
 * store's `reconcile` finds them unchanged at once.
 */

export interface Patch {
  /** keys whose value is new or replaced */
  set?: Record<string, unknown>;
  /** keys gone */
  del?: string[];
  /** keys holding an object that changed in part: its patch */
  sub?: Record<string, Patch>;
  /** keys holding a list that lost `drop` items at its start and gained `add` at its end (the log) */
  tail?: Record<string, { drop: number; add: unknown[] }>;
  /** the object's keys in their new order, when the rest would leave another order */
  keys?: string[];
}

export class PatchError extends Error {}

const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

function isObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function put(o: Record<string, unknown>, k: string, v: unknown): void {
  // (a key named "__proto__" stays a plain key, as JSON.parse makes it)
  if (k === "__proto__") Object.defineProperty(o, k, { value: v, enumerable: true, writable: true, configurable: true });
  else o[k] = v;
}

/** `patch` applied to `base` (neither is changed). Throws a PatchError when the patch does not fit the base. */
export function applyPatch<T>(view: T, patch: Patch): T {
  const base: unknown = view;
  if (!isObject(base) || !isObject(patch as unknown)) throw new PatchError("not an object");
  let out: Record<string, unknown>;
  if (patch.del && patch.del.length) {
    const gone = new Set(patch.del);
    for (const k of gone) if (!own(base, k)) throw new PatchError(`no key ${k} to remove`);
    out = {};
    for (const k of Object.keys(base)) if (!gone.has(k)) put(out, k, base[k]);
  } else {
    out = { ...base };
  }
  if (patch.sub) {
    for (const [k, sub] of Object.entries(patch.sub)) {
      const was = own(base, k) ? base[k] : undefined;
      if (!isObject(was)) throw new PatchError(`no object at ${k}`);
      put(out, k, applyPatch(was, sub));
    }
  }
  if (patch.tail) {
    for (const k of Object.keys(patch.tail)) {
      const was = own(base, k) ? base[k] : undefined;
      const t = patch.tail[k];
      if (!Array.isArray(was) || !t || !Number.isInteger(t.drop) || t.drop < 0 || t.drop > was.length || !Array.isArray(t.add)) {
        throw new PatchError(`no list to extend at ${k}`);
      }
      put(out, k, t.drop === 0 ? was.concat(t.add) : was.slice(t.drop).concat(t.add));
    }
  }
  if (patch.set) for (const k of Object.keys(patch.set)) put(out, k, patch.set[k]);
  if (patch.keys) {
    const keys = patch.keys;
    if (!Array.isArray(keys) || keys.length !== Object.keys(out).length || new Set(keys).size !== keys.length || !keys.every((k) => own(out, k))) {
      throw new PatchError("the key order names other keys");
    }
    const ordered: Record<string, unknown> = {};
    for (const k of keys) put(ordered, k, out[k]);
    out = ordered;
  }
  return out as T;
}
