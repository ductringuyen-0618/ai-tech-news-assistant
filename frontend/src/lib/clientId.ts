/**
 * Client identity — a stable, anonymous per-browser UUID used to scope
 * server-side settings/preferences without requiring auth. Sent as the
 * `X-Client-Id` header on every API request (see config/api.ts).
 */

const CLIENT_ID_KEY = "techpulse-client-id";

let cachedClientId: string | null = null;

export function getClientId(): string {
  if (cachedClientId) return cachedClientId;

  try {
    const stored = localStorage.getItem(CLIENT_ID_KEY);
    if (stored) {
      cachedClientId = stored;
      return cachedClientId;
    }
  } catch {
    // privacy mode etc. -- fall through to a fresh, unpersisted id.
  }

  const generated = crypto.randomUUID();

  try {
    localStorage.setItem(CLIENT_ID_KEY, generated);
  } catch {
    // Best-effort persistence; still usable for this session.
  }

  cachedClientId = generated;
  return cachedClientId;
}
