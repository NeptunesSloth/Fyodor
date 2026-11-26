import { ApiError } from "../services/api";

/** Ask for the profile's preferred seat; only when the server says that seat is unavailable (409 taken, 404 no such seat) ask again
 *  without it. Any other failure (a wrong code or password, too many attempts) is thrown as it is: asking again would count twice. */
export async function joinWithPreferredSeat<B extends { spectate?: boolean }, R>(
  join: (body: B & { seat?: string | null }) => Promise<R>, body: B, preferred: string | null | undefined,
): Promise<R> {
  if (!preferred || body.spectate) return join(body);
  try {
    return await join({ ...body, seat: preferred });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 409 || e.status === 404)) return join(body);
    throw e;
  }
}
