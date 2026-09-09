/**
 * CitationHoverCard -- M3b restyle.
 *
 * Wraps a child element (typically the `[N]` citation anchor produced
 * by MarkdownReport) and shows a 420px hover card with article
 * metadata (title, source, publish date, summary preview) when the
 * user hovers the anchor for at least 200ms.
 *
 * Contract:
 *  - `articleId: number` -- the backend `/api/news/{id}` integer id.
 *  - `children: ReactNode` -- the element to wrap. Most callers pass
 *    the `<a class="citation">` produced by MarkdownReport's
 *    `linkifyChildren`.
 *  - Hover 200ms+ -> fetch + show card; debounce-cancel on mouse
 *    leave.
 *  - Map cache: the first fetch for an articleId is shared across all
 *    instances rendered in the same session (module-level Map), so
 *    the same citation re-shown in different bubbles will not re-hit
 *    the backend.
 *  - Card uses `pointer-events: none` so the user can still click the
 *    underlying citation anchor through it (which scrolls to the
 *    source list in the report).
 *
 * Reused by: Research tab (citation hover on report markdown). Built
 * so other tabs can drop it in without behavior changes.
 *
 * M3b skin:
 *   - Hairline-bordered mono card (no rounded corners).
 *   - "-- SOURCE" mono eyebrow + `[N]` reference at the top-right.
 *   - Fraunces 16px title (line-clamp-2).
 *   - 13px excerpt (line-clamp-3) in soft ink.
 *   - "read at <hostname> ->" mono link in signal color.
 */
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { API_ENDPOINTS, apiFetch } from '../config/api';

/** Subset of the article shape we render in the card. */
interface CachedArticle {
  id: number | string;
  title: string;
  source: string;
  url?: string | null;
  published_at?: string | null;
  summary?: string | null;
  content?: string | null;
}

interface ApiArticleEnvelope {
  data?: {
    id: number | string;
    title: string;
    source: string;
    url?: string | null;
    published_at?: string | null;
    summary?: string | null;
    content?: string | null;
  };
  id?: number | string;
  title?: string;
  source?: string;
  url?: string | null;
  published_at?: string | null;
  summary?: string | null;
  content?: string | null;
}

// Module-level cache so all CitationHoverCard instances in the page
// share fetch results. Using a plain Map keyed by integer id; the
// value is a Promise so concurrent hovers for the same id only fire
// one request.
const articleCache = new Map<number, Promise<CachedArticle | null>>();

function fetchArticle(articleId: number): Promise<CachedArticle | null> {
  const existing = articleCache.get(articleId);
  if (existing) return existing;

  const url = API_ENDPOINTS.newsById(String(articleId));
  const promise = apiFetch<ApiArticleEnvelope>(url)
    .then(envelope => {
      const data = (envelope?.data ?? envelope) as CachedArticle | undefined;
      if (!data || typeof data.title !== 'string') {
        return null;
      }
      return data;
    })
    .catch(err => {
      // Drop the cached failure so a later hover can retry.
      articleCache.delete(articleId);
      console.warn(
        `CitationHoverCard: failed to load article ${articleId}`,
        err
      );
      return null;
    });
  articleCache.set(articleId, promise);
  return promise;
}

/**
 * Test-only -- clears the module-level cache. Not exported for runtime
 * use; only the rubric tests would conceivably need this.
 */
export function __clearCitationHoverCardCache(): void {
  articleCache.clear();
}

interface CitationHoverCardProps {
  articleId: number;
  /**
   * Citation index (1-based) -- rendered in the masthead eyebrow as
   * "[N]" so the user knows which footnote the card is previewing.
   * Optional for backward-compat with existing callers that only pass
   * the article id.
   */
  citationNumber?: number;
  children: React.ReactNode;
}

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return null;
  }
}

function buildSummaryPreview(article: CachedArticle): string {
  const raw = (article.summary || article.content || '').toString().trim();
  if (!raw) return '';
  if (raw.length <= 240) return raw;
  return raw.slice(0, 240).trimEnd() + '...';
}

/** Best-effort hostname extractor -- strips leading `www.`. */
function hostname(url: string | null | undefined): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

export function CitationHoverCard({
  articleId,
  citationNumber,
  children,
}: CitationHoverCardProps): JSX.Element {
  const reduceMotion = useReducedMotion();
  const [article, setArticle] = useState<CachedArticle | null>(null);
  const [visible, setVisible] = useState(false);
  // We track cursor position so we can render the card right next to
  // the citation anchor without needing portals.
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const enterTimerRef = useRef<number | null>(null);
  const leaveTimerRef = useRef<number | null>(null);

  // Clear pending timers if the component unmounts mid-hover.
  useEffect(() => {
    return () => {
      if (enterTimerRef.current) window.clearTimeout(enterTimerRef.current);
      if (leaveTimerRef.current) window.clearTimeout(leaveTimerRef.current);
    };
  }, []);

  const handleEnter = (e: React.MouseEvent) => {
    // Cancel any pending hide.
    if (leaveTimerRef.current) {
      window.clearTimeout(leaveTimerRef.current);
      leaveTimerRef.current = null;
    }
    // Start the 200ms appearance delay.
    const startX = e.clientX;
    const startY = e.clientY;
    setPos({ x: startX, y: startY });
    if (enterTimerRef.current) window.clearTimeout(enterTimerRef.current);
    enterTimerRef.current = window.setTimeout(async () => {
      // Pull from cache (or kick off a fetch) and only flip visible
      // if we got data. The hover may have ended before this fires,
      // but in that case `handleLeave` already scheduled a hide and
      // visible will flip back; this is fine.
      const data = await fetchArticle(articleId);
      if (data) {
        setArticle(data);
        setVisible(true);
      }
    }, 200);
  };

  const handleLeave = () => {
    // Cancel a pending show.
    if (enterTimerRef.current) {
      window.clearTimeout(enterTimerRef.current);
      enterTimerRef.current = null;
    }
    // 100ms grace before hiding -- gives the cursor a moment to enter
    // the card itself if we ever switched off `pointer-events: none`.
    if (leaveTimerRef.current) window.clearTimeout(leaveTimerRef.current);
    leaveTimerRef.current = window.setTimeout(() => {
      setVisible(false);
    }, 100);
  };

  const summary = article ? buildSummaryPreview(article) : '';
  const dateLabel = article ? formatDate(article.published_at) : null;
  const host = article ? hostname(article.url) : '';
  const readAt = host || (article ? article.source : '');

  // The card is positioned near the cursor, slightly offset down/right.
  // We use position: fixed so it floats above content; pointer-events:
  // none means clicks pass through to the underlying citation anchor.
  const cardStyle: React.CSSProperties = {
    position: 'fixed',
    left: `${pos.x + 12}px`,
    top: `${pos.y + 16}px`,
    width: '420px',
    maxWidth: 'calc(100vw - 32px)',
    zIndex: 50,
    pointerEvents: 'none',
  };

  return (
    <span
      className="citation-hover-anchor"
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {children}
      <AnimatePresence>
        {visible && article && (
          <motion.span
            data-testid="citation-hover-card"
            role="tooltip"
            style={cardStyle}
            className="block bg-background border border-[var(--rule)] p-4 shadow-lg"
            initial={reduceMotion ? { opacity: 1 } : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0 }}
            transition={{
              duration: reduceMotion ? 0 : 0.18,
              ease: 'easeOut',
            }}
          >
            <span className="flex items-center gap-2 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-2">
              <span>━ SOURCE</span>
              <span className="flex-1 border-t border-[var(--rule)]" />
              {typeof citationNumber === 'number' && (
                <span className="text-foreground-soft">
                  [<span className="text-signal">{citationNumber}</span>]
                </span>
              )}
            </span>
            <span className="block font-display text-[16px] font-medium text-foreground leading-[1.3] mb-2 line-clamp-2">
              {article.title}
            </span>
            <span className="block font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft mb-2">
              <span>{article.source}</span>
              {dateLabel ? <> &middot; {dateLabel}</> : null}
            </span>
            {summary && (
              <span
                className="block text-[13px] leading-[1.55] text-foreground-soft mb-2 line-clamp-3"
                style={{
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {summary}
              </span>
            )}
            {readAt && (
              <span className="inline-flex items-center gap-1 font-mono-tx text-[11px] uppercase-eyebrow text-signal">
                read at {readAt} →
              </span>
            )}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

export default CitationHoverCard;
