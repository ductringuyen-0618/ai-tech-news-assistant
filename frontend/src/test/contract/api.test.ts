/**
 * API CONTRACT tests — black-box assertions against the exported
 * `frontend/src/config/api.ts` surface.
 *
 * Why these tests exist
 * ---------------------
 * The frontend has 53 Playwright e2e tests that exercise rendered UI,
 * but ZERO unit-level checks on the API contract. The single most
 * common cause of a silent "frontend talks to nothing" regression is a
 * change to the endpoint shape (path drift, trailing-slash drift, base
 * URL drift) — and Playwright won't catch it because the request never
 * leaves jsdom in unit tests and a 404 in e2e looks like a backend
 * outage, not a frontend bug.
 *
 * These tests derive ENTIRELY from documented behavior:
 *
 *  - README.md API table  (paths under /api/, /health)
 *  - docs/SEARCH_API.md   (the semantic search contract)
 *  - The exhaustive comments inside `config/api.ts` itself, which call
 *    out the canonical-vs-redirect distinction for `/api/news/`
 *    (trailing slash REQUIRED) and `/api/research` (NO trailing slash).
 *    Those comments encode a backend invariant; if a future PR flips
 *    either slash, the CORS redirect bug returns silently. These tests
 *    pin the contract.
 *
 * What is intentionally NOT tested here
 * -------------------------------------
 *  - No component renders, no rendered-DOM assertions: those would
 *    require reading implementation files which are off-limits to the
 *    QA author. Component contract is the Playwright suite's job.
 *  - No backend assertions: this file mocks `global.fetch` so the
 *    contract is verified against the URL that the frontend ACTUALLY
 *    constructs, not against a live server.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  API_BASE_URL,
  API_ENDPOINTS,
  apiFetch,
} from "../../config/api";

describe("API contract — exported endpoints map", () => {
  // ---------------------------------------------------------------
  // Base URL: documented in README "Local Development" section as
  // http://localhost:8000 for unit-test / dev. The Vercel-host fork
  // points at the Fly.io backend, but in jsdom `window.location.hostname`
  // is "localhost" so the default branch must win.
  // ---------------------------------------------------------------
  it("API_BASE_URL falls back to the documented dev origin in jsdom", () => {
    // jsdom defaults `window.location.hostname` to "localhost"; the
    // module's `getApiBaseUrl()` should therefore choose the dev URL.
    expect(API_BASE_URL).toBe("http://localhost:8000");
  });

  // ---------------------------------------------------------------
  // News endpoints: README "API Endpoints → News & Articles" lists
  // /news, and the source comments in api.ts pin the trailing slash
  // as a HARD requirement (the FastAPI router 307s without it and
  // the CORS header gets dropped on the redirect).
  // ---------------------------------------------------------------
  it("news list endpoint keeps the trailing slash (CORS-safe)", () => {
    // This is THE invariant called out in the api.ts source comment:
    // sending `/api/news` triggers a 307 -> /api/news/, and FastAPI
    // emits the redirect before CORS middleware can attach the
    // Access-Control-Allow-Origin header, so the browser blocks the
    // hop and the frontend silently shows zero articles.
    expect(API_ENDPOINTS.news).toBe("/api/news/");
    expect(API_ENDPOINTS.news.endsWith("/")).toBe(true);
  });

  it("research endpoint must NOT have a trailing slash (mirror invariant)", () => {
    // The mirror of the news rule: the research router is mounted with
    // `@router.post("")` on a `/research` prefix, so the canonical
    // form is /api/research (no slash). A slash here ALSO triggers
    // a CORS-eating 307. The comment in api.ts is the spec.
    expect(API_ENDPOINTS.research).toBe("/api/research");
    expect(API_ENDPOINTS.research.endsWith("/")).toBe(false);
  });

  it("exposes the documented health-check endpoint", () => {
    // README "API Endpoints → Health & Monitoring": GET /health.
    expect(API_ENDPOINTS.health).toBe("/health");
  });

  it("exposes the documented summarize endpoint", () => {
    // README: POST /summarize (the frontend prefixes it with /api/).
    expect(API_ENDPOINTS.summarize).toBe("/api/summarize/");
  });

  it("exposes the documented semantic-search endpoint", () => {
    // README "🔍 Semantic Search (NEW): POST /search" and
    // docs/SEARCH_API.md flesh out the contract.
    expect(API_ENDPOINTS.semanticSearch).toBe("/api/search/semantic");
  });

  it("ID-bearing endpoint builders interpolate without mangling the path", () => {
    // Two of the documented endpoint builders take an ID. A common
    // regression is interpolating a number into the path with a stray
    // separator (e.g. `/api/news//42` from a `${id}/`). These build
    // tests catch that statically.
    expect(API_ENDPOINTS.newsById("abc123")).toBe("/api/news/abc123");
    expect(API_ENDPOINTS.savedResearchById(42)).toBe("/api/saved-research/42");
  });
});

describe("apiFetch — request shape contract", () => {
  // ---------------------------------------------------------------
  // `apiFetch` is the thin wrapper documented at the bottom of api.ts.
  // The contract is:
  //   - URL = API_BASE_URL + endpoint  (no extra slash munging)
  //   - default Content-Type = application/json
  //   - caller headers WIN on conflict
  //   - non-2xx throws with the status text in the message
  // ---------------------------------------------------------------
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    // Override the screaming default fetch stub from setup.ts.
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds the final URL as API_BASE_URL + endpoint, verbatim", async () => {
    await apiFetch(API_ENDPOINTS.news);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0]?.[0];
    expect(calledUrl).toBe(`${API_BASE_URL}/api/news/`);
  });

  it("sends Content-Type: application/json by default", async () => {
    await apiFetch(API_ENDPOINTS.health);
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = (init?.headers ?? {}) as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("rejects with status text when the response is non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("nope", { status: 503, statusText: "Service Unavailable" })
    );
    await expect(apiFetch(API_ENDPOINTS.health)).rejects.toThrow(
      /API request failed: 503 Service Unavailable/
    );
  });

  it("returns the parsed JSON body on success", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", uptime: 123 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const body = await apiFetch<{ status: string; uptime: number }>(
      API_ENDPOINTS.health
    );
    expect(body).toEqual({ status: "ok", uptime: 123 });
  });
});
