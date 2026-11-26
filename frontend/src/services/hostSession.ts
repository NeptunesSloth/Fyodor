/**
 * Host authority is a secret the launcher puts in the address it opens (`/#host=<secret>`); the server answers it with a
 * cookie that says "this browser is the host's" (backend app/hostauth.py, app/api/host.py). The secret leaves the address
 * bar at once. Everyone else has no cookie and is a guest, whatever address they connect from.
 */

/** Claim the host session if the address carries a secret. Returns whether the cookie was set. Run before the first API request. */
export async function claimHostSession(): Promise<boolean> {
  const secret = new URLSearchParams(location.hash.replace(/^#/, "")).get("host");
  if (!secret) return false;
  history.replaceState(null, "", location.pathname + location.search); // (first: the secret must not stay in the address bar or history)
  try {
    const res = await fetch("/api/host/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret }),
    });
    return res.ok;
  } catch {
    return false; // the server is not there: a guest until it is, which is what the page already shows
  }
}

/** Said where host tools would be, to a browser that did not claim the host session. */
export const HOST_ONLY_NOTE = "Open Fyodor from its launcher on the host computer to use host tools.";
