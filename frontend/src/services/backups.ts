/** Backups made on the host: by hand or automatically (see backend app/storage/autobackup.py). */

export interface BackupInfo { name: string; size: number; created_at: string; mtime: number; auto: boolean; reason: string | null }
export interface AutoBackupStatus { enabled: boolean; interval_minutes: number; copy_dir: string | null; last: BackupInfo | null; last_error: string | null }

/** "3.2 MB", or "48 KB" for a small pod's backup (never "0.0 MB"). */
export const backupSize = (bytes: number) => (bytes < 1e6 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

/** "12 min ago", "yesterday 21:40", "3 Oct 19:02": how long ago a backup was made, at a glance. */
export function whenMade(mtime: number, now = Date.now() / 1000): string {
  const secs = Math.max(0, now - mtime);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  const d = new Date(mtime * 1000);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const today = new Date(now * 1000);
  const days = Math.round((new Date(today.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86400000);
  if (days === 0) return `today ${time}`;
  if (days === 1) return `yesterday ${time}`;
  return `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${time}`;
}
