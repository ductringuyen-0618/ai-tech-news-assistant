/**
 * API Configuration for FastAPI Backend
 *
 * Single source of truth for backend URLs and endpoint paths.
 */
import { getClientId } from "../lib/clientId";

const getApiBaseUrl = (): string => {
  const viteEnv = (import.meta as any).env;
  if (viteEnv?.VITE_API_BASE_URL) {
    return viteEnv.VITE_API_BASE_URL;
  }
  // Production fallback -- if VITE_API_BASE_URL didn't get baked in for
  // some reason (missing .env.production, missing Vercel project env var),
  // any *.vercel.app host points at the live Fly.io backend so the app
  // still works. localhost stays on the dev backend.
  if (
    typeof window !== "undefined" &&
    window.location.hostname.includes("vercel.app")
  ) {
    return "https://techpulse-ai-backend.fly.dev";
  }
  return "http://localhost:8000";
};

export const API_BASE_URL = getApiBaseUrl();

export const API_ENDPOINTS = {
  // News endpoints. NOTE the trailing slashes: FastAPI's APIRouter has
  // redirect_slashes=True by default and serves the canonical path WITH
  // the slash. If we send `/api/news`, FastAPI replies with a 307 to
  // `/api/news/` -- but its 307 response is generated *before* the CORS
  // middleware, so the redirect has no Access-Control-Allow-Origin
  // header and the browser blocks the second hop. The fix is to call
  // the canonical (trailing-slash) URL from the start.
  news: "/api/news/",
  newsById: (id: string) => `/api/news/${id}`,
  newsSearch: "/api/news/search",
  newsIngest: "/api/news/ingest",
  newsSources: "/api/news/sources",
  newsStats: "/api/news/stats",
  newsCategories: "/api/news/categories",

  // Search endpoints
  search: "/api/search/",
  semanticSearch: "/api/search/semantic",

  // Agentic research endpoint (POST returns text/event-stream).
  // Backend mounts this with `@router.post("")` on a `/research` prefix,
  // so the canonical path is `/api/research` WITHOUT a trailing slash.
  // Sending the slash form here causes FastAPI to 307 -> the CORS headers
  // get dropped on the redirect, and the browser blocks the second hop.
  research: "/api/research",

  // Summarization endpoints (backend prefix is /api/summarize)
  summarize: "/api/summarize/",
  summarizeBatch: "/api/summarize/batch",
  summarizeArticle: (id: string) => `/api/summarize/article/${id}`,
  summarizeStatus: "/api/summarize/status",

  // Ingestion + orchestration endpoints
  ingest: "/api/ingest/",
  ingestStatus: "/api/ingest/status",
  ingestStats: "/api/ingest/stats",
  summarizePending: "/api/ingest/summarize-pending",

  // Embeddings endpoints
  embeddings: "/api/embeddings/generate",
  embeddingsStats: "/api/embeddings/stats",

  // Settings (user preferences persisted server-side)
  settings: "/api/settings/",

  // Knowledge graph (entity-extraction backed). The canvas graph tab was
  // cut; these now only back the Feed's entity filter lens -- trending
  // chips in the toolbar, and full-catalog search.
  knowledgeGraphTrending: "/api/knowledge-graph/trending",
  knowledgeGraphSearch: "/api/knowledge-graph/search",
  knowledgeGraphEntity: (id: number | string) => `/api/knowledge-graph/entity/${id}`,
  knowledgeGraphRelatedArticles: (id: number | string, limit: number = 6) =>
    `/api/knowledge-graph/related-articles/${id}?limit=${limit}`,

  // Daily digest (top stories + breakdown + trending built from DB)
  digest: "/api/digest/",
  digestDailySummary: "/api/digest/daily-summary",
  digestCurated: "/api/digest/curated",
  digestTopics: "/api/digest/topics",

  // Digest email capture (storage only -- no sending pipeline yet, see
  // docs/issues/2026-09-review-followups.md #1).
  subscribers: "/api/subscribers/",

  // Saved research (M3.M5 — persisted research reports)
  savedResearch: "/api/saved-research",
  savedResearchById: (id: number) => `/api/saved-research/${id}`,

  // Health check
  health: "/health",
  healthDetailed: "/health/detailed",
};

/**
 * Fetch wrapper with error handling.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const defaultOptions: RequestInit = {
    headers: {
      "Content-Type": "application/json",
      "X-Client-Id": getClientId(),
      ...options.headers,
    },
  };

  const response = await fetch(url, { ...defaultOptions, ...options });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}
