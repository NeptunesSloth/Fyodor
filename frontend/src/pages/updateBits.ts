/**
 * -- install update -- the Settings update section's words and its wait for the restart (kept apart from the component so they're tested).
 */
import type { UpdateResult, UpdateStatus, UpdateSummary } from "../services/update";

/** "12 KB", "48.3 MB", "1.24 GB". */
export function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

/** "version 2026-11-18a (abc1234)", "version 2026-11-18a", "commit abc1234", or null when the update doesn't say. */
export function versionText(v: { version?: string | null; commit?: string | null } | null | undefined): string | null {
  if (!v) return null;
  const commit = v.commit ? v.commit.slice(0, 12) : null;
  if (v.version) return commit ? `version ${v.version} (${commit})` : `version ${v.version}`;
  return commit ? `commit ${commit}` : null;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** The summary shown before installing: what it is, how much it replaces, where, and how it was checked. */
export function planLines(s: UpdateSummary): {
  title: string; counts: string; groups: string[]; check: string; checkOk: boolean; window: string | null; removed: string | null;
} {
  const v = versionText(s);
  const title = v ? `Fyodor ${v}` : s.zip_name ? `Update ${s.zip_name}` : "Fyodor update";
  const parts = [s.replaced ? `${s.replaced.toLocaleString()} replaced` : "", s.added ? `${s.added.toLocaleString()} new` : ""].filter(Boolean);
  const counts = `${plural(s.files, "file")}, ${sizeText(s.total_bytes)}${parts.length ? `: ${parts.join(", ")}` : ""}`;
  const groups = s.groups.map((g) => (g.folder ? `${g.name}: ${plural(g.files, "file")}, ${sizeText(g.bytes)}` : `${g.name} (${sizeText(g.bytes)})`));
  const check = s.verified
    ? "Every file matches the update's own list (size and SHA-256)."
    : "No file list in this update: each file was checked for damage, not against what it should be.";
  const window = s.closes_window ? "It replaces Fyodor's own window: that window closes while the files are copied, and a new one opens." : null;
  const removed = s.removed ? `The new version no longer uses ${plural(s.removed, "file")}; they stay in the folder and do no harm.` : null;
  return { title, counts, groups, check, checkOk: s.verified, window, removed };
}

/** What the installed copy is, for the section's first line. */
export function installedText(st: Pick<UpdateStatus, "installed">): string {
  const v = versionText(st.installed);
  return v ? `Installed: Fyodor ${v}.` : "Installed: the version this computer was set up with (no update installed from here yet).";
}

/** The last update's outcome in a sentence, or null when there was none. */
export function resultText(r: UpdateResult | null | undefined, when?: (iso: string) => string): string | null {
  if (!r) return null;
  const at = r.at ? ` (${when ? when(r.at) : r.at.replace("T", " ")})` : "";
  if (r.ok) return `Last update installed${r.version ? `: version ${r.version}` : ""}${r.files ? `, ${plural(r.files, "file")}` : ""}${at}.`;
  return `The last update didn't install${at}: ${r.message}`;
}

/** The upload's progress, as a whole percent from 0 to 100. */
export const percent = (fraction: number) => Math.max(0, Math.min(100, Math.round(fraction * 100)));

/**
 * After Install: Fyodor exits, the updater copies the files, and Fyodor starts again. Wait for its health check to stop answering, then
 * to answer again (a fixed sleep could reload the old server before it closed). "back": it answered after going away; "stuck": it never
 * went away (the updater couldn't take over); "timeout": it went away and didn't come back in time (see update.log).
 */
export async function waitForRestart(probe: () => Promise<boolean>, sleep: (ms: number) => Promise<void>,
  { step = 500, downWithin = 60_000, upWithin = 300_000 } = {}): Promise<"back" | "stuck" | "timeout"> {
  let waited = 0;
  while (await probe()) {
    if (waited >= downWithin) return "stuck";
    await sleep(step);
    waited += step;
  }
  waited = 0;
  while (!(await probe())) {
    if (waited >= upWithin) return "timeout";
    await sleep(step);
    waited += step;
  }
  return "back";
}
