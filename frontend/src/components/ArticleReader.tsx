import { useEffect, useRef, useState } from "react";
import { API_ENDPOINTS, apiFetch } from "../config/api";
import { ImageWithFallback } from "./figma/ImageWithFallback";

/**
 * ArticleReader -- on-site reading destination for an article.
 *
 * Per review-03 (reading experience): `articles.content` is a publisher
 * RSS excerpt, not licensed full text, so this deliberately does NOT try
 * to reconstruct/display "the full article". It anchors on content
 * TechPulse itself generates/owns (AI summary) plus a short excerpt, and
 * sends the reader onward to the original publisher for the rest -- the
 * SmartNews/Techmeme pattern, not republishing.
 *
 * "Related coverage" uses the purpose-built
 * `GET /knowledge-graph/related-articles/{article_id}` endpoint, which
 * does the article->entity->other-articles hop server-side and returns
 * `{article_id, primary_entity, articles}`. A 200 with an empty
 * `articles` array (no entity mentions yet) is a normal "nothing to show"
 * state, not an error.
 */

const READ_ARTICLES_KEY = "techpulse-read-articles";

function markRead(articleId: string): void {
  try {
    const raw = localStorage.getItem(READ_ARTICLES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const set = new Set<string>(Array.isArray(parsed) ? parsed.map(String) : []);
    if (set.has(articleId)) return;
    set.add(articleId);
    localStorage.setItem(READ_ARTICLES_KEY, JSON.stringify(Array.from(set)));
  } catch {
    /* ignore quota / privacy errors */
  }
}

function hostname(url: string, fallback = "source"): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

function timeAgo(dateString?: string | null): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return "";
  const hours = Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60));
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface ApiArticle {
  id: number;
  title: string;
  content?: string | null;
  summary?: string | null;
  source: string;
  url: string;
  published_at?: string | null;
  published_date?: string | null;
  created_at?: string | null;
  image_url?: string | null;
  categories?: string[] | null;
  summary_generated?: boolean | null;
  // Not part of the current backend Article model -- read defensively in
  // case another in-flight change (credibility scoring / key-insight
  // generation) starts populating these on this same response.
  credibility_score?: number | null;
  key_insights?: string[] | null;
}

interface RelatedArticle {
  id: number;
  title: string;
  source: string;
  url: string;
  published_at?: string | null;
}

interface RelatedArticlesResponse {
  article_id: number;
  primary_entity: { id: number; name: string; type: string } | null;
  articles: RelatedArticle[];
}

interface ArticleReaderProps {
  articleId: string;
  onClose?: () => void;
}

export default function ArticleReader({ articleId, onClose }: ArticleReaderProps) {
  const [currentId, setCurrentId] = useState(articleId);
  const [retryToken, setRetryToken] = useState(0);
  const [article, setArticle] = useState<ApiArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [relatedEntity, setRelatedEntity] = useState<string | null>(null);
  const [related, setRelated] = useState<RelatedArticle[] | null>(null);

  useEffect(() => {
    setCurrentId(articleId);
  }, [articleId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotFound(false);
    setArticle(null);
    setRelated(null);
    setRelatedEntity(null);

    (async () => {
      try {
        const res = await apiFetch<{ success: boolean; data: ApiArticle }>(
          API_ENDPOINTS.newsById(currentId)
        );
        if (cancelled) return;
        setArticle(res.data);
        markRead(String(res.data.id));
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "";
        if (msg.includes("404")) {
          setNotFound(true);
        } else {
          setError("Couldn't load this article. Check your connection and try again.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [currentId, retryToken]);

  // "Related coverage" -- server does the article->entity->other-articles
  // hop in one call. Empty `articles` (no entity mentions yet) is a
  // normal 200, not an error.
  useEffect(() => {
    if (!article) return;
    let cancelled = false;

    (async () => {
      try {
        const res = await apiFetch<RelatedArticlesResponse>(
          API_ENDPOINTS.knowledgeGraphRelatedArticles(article.id, 6)
        );
        if (cancelled) return;
        setRelatedEntity(res.primary_entity?.name ?? null);
        setRelated(res.articles || []);
      } catch {
        if (!cancelled) setRelated([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [article]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose?.();
  };

  useEffect(() => {
    if (!onClose) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Focus management: move focus into the dialog on open, trap Tab within
  // it while open, and restore focus to whatever triggered it (the
  // NewsCard headline, a Saved-list item, etc.) on close. None of this
  // came for free -- this is a hand-rolled dialog, not the app's Radix
  // Dialog primitive (which provides all three automatically), and
  // without it keyboard/screen-reader users had no way to reach content
  // inside the reader after it opened, or to get back to where they were
  // after closing it.
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => {
      previouslyFocused?.focus?.();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), textarea, input, select, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const publishedAt = article?.published_at || article?.published_date || article?.created_at || null;

  // Prefer the real AI summary (backend `summary` field, populated once
  // `summary_generated` is true) over a bare RSS excerpt. Either way this
  // is capped short and clearly labeled -- never presented as the full
  // article body.
  const summaryText = (article?.summary || "").trim();
  const rawExcerpt = (article?.content || "").trim();
  const isAiSummary = Boolean(article?.summary_generated) && summaryText.length > 0;
  const excerptSource = isAiSummary ? summaryText : summaryText || rawExcerpt;
  const excerpt =
    excerptSource.length > 480 ? excerptSource.slice(0, 480).trimEnd() + "..." : excerptSource;

  const keyInsights = Array.isArray(article?.key_insights) ? article!.key_insights! : [];
  const credibilityScore =
    typeof article?.credibility_score === "number" ? article.credibility_score : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 backdrop-blur-sm p-4 sm:p-8"
      onClick={handleBackdropClick}
      data-testid="article-reader"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={article ? article.title : "Article reader"}
        tabIndex={-1}
        className="relative w-full max-w-2xl my-4 sm:my-8 bg-[var(--background-tint)] border border-[var(--rule)] rounded-lg overflow-hidden outline-none"
      >
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close reader"
            data-testid="article-reader-close"
            className="absolute top-3 right-3 z-10 w-8 h-8 flex items-center justify-center rounded-full border border-[var(--rule)] bg-background/80 backdrop-blur text-foreground-soft hover:text-foreground hover:bg-background transition-colors"
          >
            {"×"}
          </button>
        )}

        {loading && (
          <div
            className="p-12 text-center font-mono-tx text-[13px] text-foreground-soft"
            data-testid="article-reader-loading"
          >
            Loading article…
          </div>
        )}

        {!loading && notFound && (
          <div className="p-12 text-center" data-testid="article-reader-not-found">
            <p className="text-foreground mb-2">Article not found.</p>
            <p className="text-[13px] text-foreground-soft">
              It may have been archived or removed.
            </p>
          </div>
        )}

        {!loading && error && (
          <div className="p-12 text-center" data-testid="article-reader-error">
            <p className="text-foreground mb-3">{error}</p>
            <button
              type="button"
              onClick={() => setRetryToken((t) => t + 1)}
              className="text-[13px] font-medium px-3 py-1.5 border border-[var(--rule)] rounded-md hover:bg-background/60 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && !notFound && article && (
          <div>
            {article.image_url && (
              <div className="relative aspect-[16/9] bg-[var(--background-deep)] overflow-hidden">
                <ImageWithFallback
                  src={article.image_url}
                  alt={article.title}
                  className="w-full h-full object-cover"
                />
              </div>
            )}

            <div className="p-5 sm:p-6">
              <div className="font-mono-tx text-[11px] uppercase-eyebrow flex items-center gap-2 mb-3">
                <span className="text-gray-500 uppercase-eyebrow">{article.source}</span>
                {timeAgo(publishedAt) && (
                  <>
                    <span className="text-foreground-soft">.</span>
                    <span className="text-foreground-soft">{timeAgo(publishedAt)}</span>
                  </>
                )}
                {credibilityScore !== null && (
                  <>
                    <span className="text-foreground-soft">.</span>
                    <span className="text-foreground-soft" title="Source credibility signal">
                      credibility {credibilityScore}
                    </span>
                  </>
                )}
              </div>

              <h1
                className="font-display text-foreground mb-4"
                style={{ fontSize: "24px", lineHeight: 1.25, letterSpacing: "-0.02em" }}
              >
                {article.title}
              </h1>

              {excerpt ? (
                <div className="mb-4">
                  <div className="text-[11px] uppercase tracking-wide text-foreground-mute mb-1.5">
                    {isAiSummary ? "TechPulse AI summary" : `Excerpt from ${article.source}`}
                  </div>
                  <p
                    data-testid="article-reader-summary"
                    className="text-[15px] leading-[1.6] text-foreground"
                    style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}
                  >
                    {excerpt}
                  </p>
                </div>
              ) : (
                <p className="text-[14px] italic text-foreground-mute mb-4">
                  No summary yet -- read the full story at the source below.
                </p>
              )}

              {keyInsights.length > 0 && (
                <div className="border border-[var(--rule)] p-3 rounded-md mb-4">
                  <div className="text-[11px] uppercase tracking-wide text-foreground-mute mb-2">
                    Key insights
                  </div>
                  <ul className="space-y-1.5">
                    {keyInsights.map((insight, idx) => (
                      <li
                        key={idx}
                        className="text-[14px] leading-[1.55] text-foreground flex items-start gap-2"
                      >
                        <span style={{ color: "var(--accent-signal)" }} className="mt-1.5 leading-none">
                          {"●"}
                        </span>
                        <span style={{ overflowWrap: "anywhere" }}>{insight}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="article-reader-outbound-link"
                className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-4 py-2.5 mb-1 text-[14px] font-medium rounded-md border border-[var(--accent-signal)] bg-signal-wash text-signal hover:bg-[var(--accent-signal)] hover:text-white transition-colors"
              >
                Read the full story at {hostname(article.url)} {"→"}
              </a>

              {related && related.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[var(--rule)]" data-testid="article-reader-related">
                  <div className="text-[11px] uppercase tracking-wide text-foreground-mute mb-2">
                    Related coverage{relatedEntity ? ` — ${relatedEntity}` : ""}
                  </div>
                  <ul className="space-y-2">
                    {related.map((r) => (
                      <li key={r.id}>
                        <button
                          type="button"
                          onClick={() => setCurrentId(String(r.id))}
                          className="w-full text-left text-[13px] leading-[1.4] text-foreground-soft hover:text-signal py-1 group"
                        >
                          <span className="group-hover:underline">{r.title}</span>
                          <span className="text-foreground-mute"> — {r.source}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
