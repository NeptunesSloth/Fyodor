import { ApiError, api } from "./api";
import { seatToken } from "./games";

export type AssetKind = "playmat" | "card_back" | "token_art" | "counter_art" | "utility" | "reference" | "dice_skin" | "table_preset";

export const ASSET_KINDS: [AssetKind, string][] = [
  ["playmat", "Playmats"],
  ["card_back", "Card backs"],
  ["token_art", "Token art"],
  ["counter_art", "Counter art"],
  ["utility", "Utility objects"],
  ["reference", "Reference cards"],
  ["dice_skin", "Dice skins"],
  ["table_preset", "Table presets"],
];

export interface Asset {
  id: string;
  kind: AssetKind;
  name: string;
  sha256: string;
  mime: string;
  width: number;
  height: number;
  size: number;
  url: string;
  created_at: string;
  updated_at: string;
  used_by?: string[];
}

export const listAssets = (kind?: AssetKind) => api.get<Asset[]>(`/assets${kind ? `?kind=${kind}` : ""}`);
export const renameAsset = (id: string, name: string) => api.patch<Asset>(`/assets/${id}`, { name });
export const duplicateAsset = (id: string) => api.post<Asset>(`/assets/${id}/duplicate`);
export const deleteAsset = (id: string, force = false) => api.del<void>(`/assets/${id}${force ? "?force=true" : ""}`);

const MAX = 20 * 1024 * 1024;

async function sendFile(method: "POST" | "PUT", path: string, file: Blob, gameId?: string): Promise<Asset> {
  if (file.size > MAX) throw new ApiError(413, "Images are limited to 20 MB");
  const headers: Record<string, string> = { "Content-Type": "application/octet-stream" };
  const token = gameId ? seatToken(gameId) : null;
  if (token) headers["X-Seat-Token"] = token;
  const res = await fetch(`/api${path}`, { method, headers, body: file });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, typeof detail.detail === "string" ? detail.detail : res.statusText, detail);
  }
  return (await res.json()) as Asset;
}

/** Upload an image (validated by content on the host). `gameId` lets a LAN player use their seat. */
export const uploadAsset = (file: Blob, kind: AssetKind, name: string, gameId?: string) =>
  sendFile("POST", `/assets?kind=${kind}&name=${encodeURIComponent(name.slice(0, 80))}`, file, gameId);
export const replaceAsset = (id: string, file: Blob) => sendFile("PUT", `/assets/${id}/file`, file);

export const fmtSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
