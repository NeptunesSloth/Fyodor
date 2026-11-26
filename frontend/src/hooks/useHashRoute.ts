import { useEffect, useState } from "react";

export interface Route {
  path: string[];
  query: URLSearchParams;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path = "", query = ""] = raw.split("?");
  return { path: path.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(query) };
}

// -- leave guard -- a page with unsaved work (the deck editor) may refuse to be left: a link, the top bar, navigate() or the
// browser's Back. The address changes before the app hears of it, so a refusal puts the page's own address back (replaceState:
// no second hashchange) and the page never unmounts.
// (read when first needed, not at import: main.tsx takes a seat token or the host secret off the address before anything renders,
// and the address remembered here must be the cleaned one)
let accepted: string | null = null;
/** The address the app last accepted as the page it is on. */
export function acceptedHash(): string {
  accepted ??= window.location.hash;
  return accepted;
}
let leaveGuard: (() => boolean) | null = null;

/** While set, `guard` runs before the app leaves the current page; returning false stays. Returns the function that clears it. */
export function setLeaveGuard(guard: () => boolean): () => void {
  leaveGuard = guard;
  return () => {
    if (leaveGuard === guard) leaveGuard = null;
  };
}

function mayLeave(): boolean {
  const next = window.location.hash;
  if (next !== acceptedHash() && leaveGuard && !leaveGuard()) {
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${acceptedHash()}`);
    return false;
  }
  accepted = next;
  return true;
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState(() => {
    acceptedHash();
    return parse();
  });
  useEffect(() => {
    const onChange = () => {
      if (mayLeave()) setRoute(parse());
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = path.startsWith("/") ? path : `/${path}`;
}
