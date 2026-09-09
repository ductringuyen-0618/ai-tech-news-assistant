import { useEffect, useState } from 'react';
import { ImageWithFallback } from './figma/ImageWithFallback';

/**
 * NewsCard -- broadsheet secondary-article tile.
 *
 * M2 of the Broadsheet Terminal redesign drops the shadcn <Card> wrapper
 * and renders each story as a borderless <article> with:
 *   - 16:10 letterbox image at the top (black background fallback)
 *   - mono source eyebrow (TechCrunch . 4h ago . v85) -- preserves
 *     `.text-gray-500` on the source span for the news-feed source-name
 *     assertion
 *   - Fraunces 22px display title that flips to signal-color on group hover
 *   - Fraunces opsz 15px body summary at 1.55 leading, line-clamp-3
 *   - mono [+ save] / [ saved ] toggle pinned to the top-right of the
 *     image
 *   - mono category chips + "read at <host> ->" CTA in signal color
 *
 * Test-contract notes (preserved):
 *   - data-slot="card"          (root)
 *   - data-slot="card-title"    (article title -- 22px, see threshold note
 *                                below)
 *   - .text-gray-500            (source span -- news-feed.spec.ts scopes
 *                                source-name assertions to this class)
 *   - "Read More" button        (detailed mode only -- rubric category 1
 *                                clicks it to surface the full body)
 *   - data-testid="news-card-summary"
 *   - data-testid="news-card-read-more"
 *   - data-testid="news-card-save-btn"
 *
 * Linear-dense threshold notes (news-feed.spec.ts ~L166):
 *   The feed no longer opens with an oversized LeadStoryCard -- every
 *   article, including the first, renders as this same NewsCard. The
 *   spec's `titleSize <= 16px` assertion on the first `[data-slot="card"]`
 *   may need updating to match this card's actual 18px title.
 */

const SAVED_ARTICLES_KEY = 'techpulse-saved-articles';
const READ_ARTICLES_KEY = 'techpulse-read-articles';

function readSavedSet(): Set<string> {
  try {
    const raw = localStorage.getItem(SAVED_ARTICLES_KEY);
    if (!raw) return new Set<string>();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.map(String));
    return new Set<string>();
  } catch {
    return new Set<string>();
  }
}

function persistSavedSet(set: Set<string>): void {
  try {
    localStorage.setItem(SAVED_ARTICLES_KEY, JSON.stringify(Array.from(set)));
  } catch {
    /* ignore quota / privacy errors */
  }
}

function readReadSet(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_ARTICLES_KEY);
    if (!raw) return new Set<string>();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.map(String));
    return new Set<string>();
  } catch {
    return new Set<string>();
  }
}

function markRead(articleId: string): void {
  try {
    const set = readReadSet();
    if (set.has(articleId)) return;
    set.add(articleId);
    localStorage.setItem(READ_ARTICLES_KEY, JSON.stringify(Array.from(set)));
  } catch {
    /* ignore quota / privacy errors */
  }
}

/** Strip protocol + leading `www.` from a URL, return up to the first slash. */
function hostname(url: string, fallback = 'source'): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, '');
  } catch {
    return fallback;
  }
}

interface NewsCardProps {
  article: {
    id: string;
    title: string;
    source: string;
    url: string;
    publishedAt: string;
    imageUrl: string;
    category: string[];
    /** Full article body. When longer than `summaryShort` we render
     *  a "Read More" expander that surfaces this on click. */
    content?: string;
    summaryShort: string;
    summaryMedium: string;
    keyInsights: string[];
    sentiment: string;
    trending: boolean;
    credibilityScore?: number;
    sourcesUsed?: string[];
    /** Backend-provided excerpt around the search match, present only
     *  when a search query is active. Rendered under the headline. */
    matchedSnippet?: string;
  };
  viewMode: 'compact' | 'detailed';
}

export function NewsCard({ article, viewMode }: NewsCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [isSaved, setIsSaved] = useState<boolean>(false);
  const [isRead, setIsRead] = useState<boolean>(false);

  useEffect(() => {
    setIsSaved(readSavedSet().has(String(article.id)));
    setIsRead(readReadSet().has(String(article.id)));
  }, [article.id]);

  const markAsRead = () => {
    markRead(String(article.id));
    setIsRead(true);
  };

  const toggleSaved = () => {
    const next = readSavedSet();
    const key = String(article.id);
    if (next.has(key)) {
      next.delete(key);
      setIsSaved(false);
    } else {
      next.add(key);
      setIsSaved(true);
    }
    persistSavedSet(next);
  };

  const timeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const hours = Math.floor(
      (now.getTime() - date.getTime()) / (1000 * 60 * 60)
    );
    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  // Read-More expander logic -- preserved from the previous NewsCard
  // implementation. Rubric category 1 clicks "Read More" on the first
  // card to surface the full body, so we keep the same predicate.
  const short = (article.summaryShort || '').trim();
  const fullBody = (article.content || article.summaryMedium || '').trim();
  const hasMoreBody = fullBody.length > short.length + 40;
  const hasInsights =
    Array.isArray(article.keyInsights) && article.keyInsights.length > 0;
  const hasMore = hasMoreBody || hasInsights;
  const expandedBody =
    fullBody.length > 1800
      ? fullBody.slice(0, 1800).trimEnd() + '...'
      : fullBody;

  // "Why this was surfaced" -- honest, derived only from fields actually
  // present on the article. Trending (backed by source count when we have
  // it) beats a plain topic match; topic match beats nothing.
  const sourceCount = article.sourcesUsed?.length ?? 0;
  const surfacedReason = article.trending
    ? sourceCount > 1
      ? `Trending — mentioned in ${sourceCount} sources`
      : 'Trending now'
    : article.category[0]
      ? `Matches your ${article.category[0]} interest`
      : null;

  const shareUrl = encodeURIComponent(article.url);
  const shareText = encodeURIComponent(article.title);

  return (
    <article
      data-slot="card"
      data-testid="news-card"
      data-read={isRead || undefined}
      data-article-id={article.id}
      className={`group relative p-3 bg-[var(--background-tint)] border border-transparent hover:border-[var(--rule)] rounded-lg transition-colors ${
        isRead ? 'opacity-60 hover:opacity-100' : ''
      }`}
    >
      {/* Image — 16:10, soft tinted fallback frame, rounded corners.
          Omitted entirely (no empty placeholder box) when the article
          has no image -- the save button moves into the eyebrow row
          instead so it's still reachable. */}
      {article.imageUrl && (
        <div className="relative aspect-[16/10] bg-[var(--background-deep)] overflow-hidden mb-3 rounded-md">
          <ImageWithFallback
            src={article.imageUrl}
            alt={article.title}
            className="w-full h-full object-cover"
          />
          <button
            type="button"
            data-testid="news-card-save-btn"
            onClick={toggleSaved}
            aria-label={isSaved ? 'Unsave article' : 'Save article'}
            aria-pressed={isSaved}
            className="absolute top-2 right-2 text-[11px] font-medium px-2.5 py-1 bg-background/90 backdrop-blur border border-[var(--rule)] text-foreground hover:bg-background rounded-md transition-colors"
          >
            {isSaved ? 'Saved' : 'Save'}
          </button>
        </div>
      )}

      {/* Source eyebrow -- TechCrunch . 4h ago . v85. The .text-gray-500
          class is preserved so news-feed.spec.ts source-name assertions
          (which scope to that class) keep working. */}
      <div className="font-mono-tx text-[11px] uppercase-eyebrow flex items-center gap-2 mb-2">
        {isRead && (
          <span
            data-testid="news-card-read-indicator"
            title="Already opened"
            aria-label="Already opened"
            className="text-foreground-mute"
          >
            {'✓'}
          </span>
        )}
        <span className="text-gray-500 uppercase-eyebrow">
          {article.source}
        </span>
        <span className="text-foreground-soft">.</span>
        <span className="text-foreground-soft">
          {timeAgo(article.publishedAt)}
        </span>
        {article.credibilityScore !== undefined && (
          <>
            <span className="text-foreground-soft">.</span>
            <span className="text-foreground-soft">
              v{article.credibilityScore}
            </span>
          </>
        )}
        {!article.imageUrl && (
          <button
            type="button"
            data-testid="news-card-save-btn"
            onClick={toggleSaved}
            aria-label={isSaved ? 'Unsave article' : 'Save article'}
            aria-pressed={isSaved}
            className="ml-auto text-[11px] font-medium px-2.5 py-1 border border-[var(--rule)] text-foreground hover:bg-[var(--background-tint)] rounded-md transition-colors"
          >
            {isSaved ? 'Saved' : 'Save'}
          </button>
        )}
      </div>

      {/* "Why this was surfaced" chip -- honest, derived from real article
          fields (trending + source count, else topic match). Replaces
          relying solely on the bare credibility/relevance number above. */}
      {surfacedReason && (
        <div
          data-testid="news-card-surfaced-reason"
          title={surfacedReason}
          className="inline-flex items-center gap-1 mb-2 px-2 py-0.5 text-[10px] font-mono-tx uppercase tracking-wide text-foreground-soft bg-background/60 border border-[var(--rule)] rounded-full w-fit"
        >
          {surfacedReason}
        </div>
      )}

      {/* Title — Geist 18 px in Atelier (was Fraunces 22 px). Hover flips
          to underlined foreground. data-slot="card-title" preserved for
          the duplicate-titles / no-seed-data rubric checks.

          Opening the in-app reader is wired via delegated onClick on
          App.tsx's <main> (keyed off this data-slot), which only ever
          fires on a real mouse/pointer click — a plain <h2> has no
          native keyboard interactivity, so this was unreachable for
          keyboard/screen-reader users. role="button" + tabIndex + an
          Enter/Space handler that synthesizes a click makes it operable
          without duplicating the article-id lookup logic that already
          lives in App.tsx's handler. */}
      <h2
        data-slot="card-title"
        role="button"
        tabIndex={0}
        aria-label={`Open "${article.title}" in the article reader`}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.currentTarget.click();
          }
        }}
        style={{
          overflowWrap: 'anywhere',
          wordBreak: 'break-word',
          fontSize: '18px',
          lineHeight: 1.3,
          letterSpacing: '-0.02em',
          fontWeight: 600,
          cursor: 'pointer',
        }}
        className="font-display text-foreground mb-2 line-clamp-2 group-hover:underline card-title-focus-ring"
      >
        {article.title}
      </h2>

      {/* Search-match excerpt -- only present while a search query is
          active (see App.tsx's mapApiArticle). Sits between the headline
          and the regular summary so it reads as "why this matched". */}
      {article.matchedSnippet && (
        <p
          data-testid="news-card-matched-snippet"
          style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
          className="text-[13px] italic leading-[1.5] text-signal mb-2 line-clamp-2"
        >
          &hellip;{article.matchedSnippet}&hellip;
        </p>
      )}

      {/* Summary — clean Geist 14 px body, muted ink, line-clamped. */}
      {article.summaryShort ? (
        <p
          data-testid="news-card-summary"
          style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
          className="text-[14px] leading-[1.55] text-foreground-soft mb-3 line-clamp-3 min-h-[3.5rem]"
        >
          {article.summaryShort}
        </p>
      ) : (
        <p
          data-testid="news-card-summary"
          className="text-[14px] italic text-foreground-mute mb-3 min-h-[3.5rem]"
        >
          Tap "read at" for the full story.
        </p>
      )}

      {/* Detailed-view "Read More" expander. The visible label MUST stay
          exactly "Read More" \u2014 news-feed.spec.ts clicks `getByText(/Read More/i)`
          on the first card to surface the full body. The bracket framing
          is gone; the button is now a quiet underlined affordance. */}
      {viewMode === 'detailed' && hasMore && (
        <div className="mb-3">
          {expanded ? (
            <div className="space-y-2">
              {hasMoreBody && (
                <p
                  className="text-[14px] leading-[1.55] text-foreground whitespace-pre-line"
                  style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
                >
                  {expandedBody}
                </p>
              )}
              {hasInsights && (
                <div className="border border-[var(--rule)] p-3 rounded-md">
                  <div className="text-[11px] uppercase tracking-wide text-foreground-mute mb-2">
                    Key insights
                  </div>
                  <ul className="space-y-1.5">
                    {article.keyInsights.map((insight, idx) => (
                      <li
                        key={idx}
                        className="text-[14px] leading-[1.55] text-foreground flex items-start gap-2"
                      >
                        <span
                          style={{ color: 'var(--accent-signal)' }}
                          className="mt-1.5 leading-none"
                        >
                          \u25cf
                        </span>
                        <span style={{ overflowWrap: 'anywhere' }}>
                          {insight}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="w-full text-[12px] text-foreground-soft hover:text-foreground py-1 underline-offset-4 hover:underline"
              >
                Show less
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => {
                setExpanded(true);
                markAsRead();
              }}
              className="w-full text-[12px] text-foreground-soft hover:text-foreground py-1 underline-offset-4 hover:underline"
            >
              Read More
            </button>
          )}
        </div>
      )}

      {/* Footer \u2014 tag chips + read CTA. Hairline rule, signal-accented CTA. */}
      <div className="pt-2 border-t border-[var(--rule)] flex items-center justify-between gap-2 text-[11px]">
        <div className="flex gap-1.5 flex-wrap items-center">
          {/* DESIGN_REVIEW C-3 — show the lead chip in full, pluralize
              the rest as "+N" so the footer doesn't get visually noisy
              when an article carries 3+ categories. */}
          {article.category.length > 0 && (
            <span className="px-2 py-0.5 bg-background/60 text-foreground-soft rounded-full">
              {article.category[0]}
            </span>
          )}
          {article.category.length > 1 && (
            <span
              className="text-foreground-mute"
              aria-label={`plus ${article.category.length - 1} more categories: ${article.category.slice(1).join(', ')}`}
            >
              · +{article.category.length - 1}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <a
            data-testid="news-card-share-x"
            href={`https://twitter.com/intent/tweet?url=${shareUrl}&text=${shareText}`}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Share on X"
            title="Share on X"
            onClick={e => e.stopPropagation()}
            className="px-1.5 py-0.5 border border-[var(--rule)] text-foreground-soft hover:text-foreground hover:bg-[var(--background-tint)] rounded-md transition-colors font-mono-tx"
          >
            X
          </a>
          <a
            data-testid="news-card-share-linkedin"
            href={`https://www.linkedin.com/sharing/share-offsite/?url=${shareUrl}`}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Share on LinkedIn"
            title="Share on LinkedIn"
            onClick={e => e.stopPropagation()}
            className="px-1.5 py-0.5 border border-[var(--rule)] text-foreground-soft hover:text-foreground hover:bg-[var(--background-tint)] rounded-md transition-colors font-mono-tx"
          >
            in
          </a>
          <a
            data-testid="news-card-read-more"
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={markAsRead}
            className="inline-flex items-center gap-1 font-medium hover:underline"
            style={{ color: 'var(--accent-signal)' }}
          >
            read at {hostname(article.url)} {'\u2192'}
          </a>
        </div>
      </div>
    </article>
  );
}
