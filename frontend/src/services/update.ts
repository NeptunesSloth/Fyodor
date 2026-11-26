/**
 * -- install update -- Settings → Install update… (host computer only; backend app/api/updates.py): the update zip is sent to this computer's
 * own Fyodor, which checks it and says what it would replace; installing it saves every game, tells the players, and restarts Fyodor.
 */
import { api } from "./api";

/** What an uploaded update would do (app/storage/update.py Plan.summary). */
export interface UpdateSummary {
  files: number;
  total_bytes: number;
  replaced: number;
  added: number;
  version: string | null;
  commit: string | null;
  built_at: string | null;
  /** every file matched the update's manifest (size and sha256) */
  verified: boolean;
  /** files the new version no longer uses (left in place) */
  removed: number;
  removed_sample: string[];
  warnings: string[];
  /** the top-level folders (and single files) it touches */
  groups: { name: string; files: number; bytes: number; folder: boolean }[];
  /** it replaces Fyodor's own window (browser/): that window closes and a new one opens */
  closes_window: boolean;
  zip_name: string | null;
}

/** What the updater did last (update-result.json, written by the updater script). */
export interface UpdateResult { ok: boolean; message: string; files?: number; version?: string; at?: string }

export interface UpdateStatus {
  available: boolean;
  /** why this copy can't install updates (a source checkout, not Windows) */
  reason: string | null;
  install_dir: string | null;
  installed: { version: string | null; commit: string | null; built_at: string | null } | null;
  pending: UpdateSummary | null;
  last: UpdateResult | null;
  log: string;
  can_restart: boolean;
}

export const updateStatus = () => api.get<UpdateStatus>("/update");
export const discardUpdate = () => api.del("/update");
export const applyUpdate = () => api.post<{ restarting: boolean; closes_window: boolean; files: number; version: string | null }>("/update/apply", {});

/** Send the zip to this computer's Fyodor (XHR: fetch can't report upload progress). Resolves with what it found in it; rejects with its reason. */
export function uploadUpdate(file: File, onProgress: (fraction: number) => void): Promise<UpdateSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/update/upload");
    xhr.setRequestHeader("Content-Type", "application/zip");
    xhr.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.upload.onload = () => onProgress(1);
    xhr.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* (an empty or non-JSON answer) */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as UpdateSummary);
      else reject(new Error(uploadError(xhr.status, body)));
    };
    xhr.onerror = () => reject(new Error("The update couldn't be sent to Fyodor (is it still running?)"));
    xhr.send(file);
  });
}

/** The words for a refused upload: the server's reason, else what the status means. */
export function uploadError(status: number, body: unknown): string {
  const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
  if (typeof detail === "string" && detail) return detail;
  if (status === 413) return "That file is too large to be a Fyodor update";
  if (status === 403) return "Updates are installed on the host computer (the one running Fyodor)";
  return `The update was refused (${status})`;
}
