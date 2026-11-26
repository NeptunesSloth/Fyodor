import { useEffect, useState } from "react";
import { api, getHealth } from "./api";

/** The table's invite link over the internet (backend app/api/share.py). Host cookie only. */
export interface ShareStatus {
  shared: boolean;
  state: "stopped" | "starting" | "running" | "failed";
  /** why it is unavailable, or why it failed */
  reason: string | null;
  link: string | null;
  has_password: boolean;
  available: boolean;
}

export const getShare = (gameId: string) => api.get<ShareStatus>(`/games/${gameId}/share`);
/** The password is sent only when given (a table that already has one keeps it). */
export const startShare = (gameId: string, password?: string) =>
  api.post<ShareStatus>(`/games/${gameId}/share`, password ? { password } : {});
export const stopShare = (gameId: string) => api.del<ShareStatus>(`/games/${gameId}/share`);

let tunnelAsked: Promise<boolean> | null = null;
/** Whether this page was reached through the invite link (GET /api/health, asked once). */
export const isTunnel = (): Promise<boolean> => (tunnelAsked ??= getHealth().then((h) => h.tunnel === true, () => false));

/** True on the invite link; false until known and anywhere else. */
export function useTunnel(): boolean {
  const [t, setT] = useState(false);
  useEffect(() => {
    let live = true;
    void isTunnel().then((v) => live && setT(v));
    return () => { live = false; };
  }, []);
  return t;
}
