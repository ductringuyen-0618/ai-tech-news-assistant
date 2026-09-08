import { useEffect, useState } from "react";
import { toast } from "sonner";
import { NewsCard } from "./NewsCard";
import { API_ENDPOINTS, apiFetch } from "../config/api";
import { Loader2, AlertCircle } from "lucide-react";

/**
 * SavedArticlesList -- renders the articles a reader has filed via
 * NewsCard's "Save" button.
 *
 * NewsCard writes saved article ids to `localStorage['techpulse-saved-
 * articles']` but nothing previously read that key back, so a "Saved"
 * confirmation pointed at data the reader could never retrieve. This
 * component closes that loop: it reads the id list itself, fetches each
 * article by id (there's no batch-by-ids endpoint on the backend, so a
 * small saved list is fetched via one GET per id), and renders them with
 * the same NewsCard used on the main feed so the visual language matches.
 *
 * Styled to sit alongside SavedResearchList on the Saved page -- same
 * masthead / mono-eyebrow / empty-state conventions.
 */

const SAVED_ARTICLES_KEY = "techpulse-saved-articles";

function readSavedIds(): string[] {
  try {
    const raw = localStorage.getItem(SAVED_ARTICLES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function writeSavedIds(ids: string[]): void {
  try {
    localStorage.setItem(SAVED_ARTICLES_KEY, JSON.stringify(ids));
  } catch {
    /* ignore quota / privacy errors */
  }
}

/** Raw API article -> the shape NewsCard expects. Mirrors App.tsx's
 *  `mapApiArticle` (not exported there) so saved cards render identically
 *  to the main feed. */
function mapApiArticle(a: any) {
  const summary = (a.summary || "").toString().trim();
  const content = (a.content || "").toString().trim();
  const body = content.length > summary.length * 1.5 ? content : (summary || content);
  const summaryShort = !body
    ? ""
    : body.length > 280
      ? body.slice(0, 280).trimEnd() + "..."
      : body;
  const summaryMedium = !body
    ? ""
    : body.length > 800
      ? body.slice(0, 800).trimEnd() + "..."
      : body;
  return {
    id: a.id,
    title: a.title,
    content: a.content,
    summaryShort,
    summaryMedium,
    url: a.url,
    publishedAt: a.published_at,
    imageUrl: a.image_url || "",
    category: a.categories || [],
    source: a.source,
    credibilityScore: 85,
    trending: false,
    sentiment: "neutral",
    keyInsights: [],
    sourcesUsed: [a.source],
  };
}

interface BaseResponseLike {
  success: boolean;
  message?: string;
  data: any;
}

export default function SavedArticlesList() {
  const [articles, setArticles] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchSaved() {
    setLoading(true);
    setError(null);
    const ids = readSavedIds();

    if (ids.length === 0) {
      setArticles([]);
      setLoading(false);
      return;
    }

    const results = await Promise.allSettled(
      ids.map((id) => apiFetch<BaseResponseLike>(API_ENDPOINTS.newsById(id)))
    );

    const loaded: any[] = [];
    const staleIds: string[] = [];

    results.forEach((result, idx) => {
      if (result.status === "fulfilled" && result.value?.data) {
        loaded.push(mapApiArticle(result.value.data));
      } else {
        // Article was deleted/archived server-side since it was saved --
        // drop its id so it stops silently failing on every future visit.
        staleIds.push(ids[idx]);
      }
    });

    if (staleIds.length > 0) {
      writeSavedIds(ids.filter((id) => !staleIds.includes(id)));
    }

    if (loaded.length === 0 && staleIds.length > 0 && ids.length > 0) {
      // Every saved id failed to resolve -- surface this distinctly from
      // "nothing saved" so it doesn't read as if the feature is empty.
      setError("Couldn't load your saved articles. They may have been removed.");
      setArticles([]);
    } else {
      setArticles(loaded);
    }
    setLoading(false);
  }

  useEffect(() => {
    void fetchSaved();
  }, []);

  function handleRemove(id: string) {
    const prevIds = readSavedIds();
    writeSavedIds(prevIds.filter((savedId) => savedId !== id));
    setArticles((prev) => (prev ? prev.filter((a) => String(a.id) !== id) : prev));
    toast.success("Removed from saved articles");
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4" data-testid="saved-articles-list">
      <header className="space-y-1 border-b-2 border-[var(--foreground)] pb-3">
        <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          ━ THE CLIPPING FILE
        </div>
        <h2 className="font-display text-[28px] font-medium tracking-tight text-foreground leading-[1.1]">
          Saved Articles
        </h2>
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          stories you've filed away · click Save on any card to add more
        </p>
      </header>

      {loading && (
        <div className="flex items-center justify-center py-12 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>loading saved articles...</span>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-3 py-4 border-t-2 border-[var(--accent-signal)] px-4 bg-[var(--background-tint)]">
          <AlertCircle className="w-5 h-5 text-signal flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-display text-[18px] font-medium text-foreground">
              Failed to load saved articles
            </p>
            <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mt-1">
              {error}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void fetchSaved()}
            className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal"
          >
            [ retry ]
          </button>
        </div>
      )}

      {!loading && !error && articles && articles.length === 0 && (
        <div className="text-center py-12 space-y-2" data-testid="saved-articles-empty">
          <p className="font-mono-tx text-[24px] text-foreground-soft">▌</p>
          <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
            No saved articles yet — click Save on any story to file it here.
          </p>
        </div>
      )}

      {!loading && !error && articles && articles.length > 0 && (
        <div className="space-y-3">
          {articles.map((article) => (
            <div
              key={article.id}
              data-testid="saved-articles-item"
              className="space-y-1"
            >
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => handleRemove(String(article.id))}
                  data-testid="saved-articles-remove-btn"
                  aria-label={`Remove saved article: ${article.title}`}
                  className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft hover:text-signal transition-colors"
                >
                  [ × remove ]
                </button>
              </div>
              <NewsCard article={article} viewMode="compact" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
