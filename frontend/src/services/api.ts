/** Thin typed wrapper around the backend REST API. All paths are same-origin (proxied in dev). */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
  const headers: Record<string, string> = { ...extraHeaders };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => undefined);
    }
    const msg =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? formatDetail((detail as { detail: unknown }).detail)
        : `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, msg, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join("; ");
  }
  return JSON.stringify(detail);
}

export const api = {
  get: <T>(path: string, headers?: Record<string, string>) => request<T>("GET", path, undefined, headers),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, body ?? {}, headers),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string, headers?: Record<string, string>) => request<T>("DELETE", path, undefined, headers),
};

export interface Health {
  status: string;
  version: string;
  card_database?: CardDbStats;
  games_active?: number;
  /** Set when the app database was damaged and Fyodor started with a fresh one. */
  recovery?: { reason: string; moved_to: string | null; backups: string[] };
  /** Tables brought back after a crash or restart. */
  recovered_tables?: { game_id: string; name: string }[];
}

export interface CardDbStats {
  available: boolean;
  printings: number;
  oracle_cards: number;
  tokens: number;
  images: number;
  bulk_type: string | null;
  bulk_updated_at: string | null;
  imported_at: string | null;
}

export const getHealth = () => api.get<Health>("/health");
