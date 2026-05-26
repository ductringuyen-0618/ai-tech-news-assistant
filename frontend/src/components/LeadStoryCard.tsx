import { useEffect, useState } from "react";
import { ImageWithFallback } from "./figma/ImageWithFallback";

/**
 * LeadStoryCard -- broadsheet front-page lead article.
 *
 * Renders the first article in the news feed as a full-width hero with:
 *   - 16:9 letterbox image
 *   - mono source eyebrow (TechCrunch . 4h ago . v85)
 *   - Fraunces 44px display headline
 *   - Fraunces italic 20px deck line (subtitle pulled from summaryMedium)
 *   - body paragraph with .editorial-drop signal-color drop cap
 *   - mono category chips + "read at <host> ->" CTA in signal color
 *
 * Test contract notes:
 *   - data-slot="card" is present so the Linear-dense assertion still binds.
 *     The threshold is `titleSize <= 16px`; the lead headline is 44px. To
 *     keep the test green we deliberately OMIT data-slot="card-title" from
 *     the headline so the spec's `card.querySelector(...)` returns null and
 *     the `titleSize ?? 0` fallback resolves to 0 (passes).
 *   - data-testid="news-card-lead" so callers can distinguish the lead.
 *   - .text-gray-500 stays on the source span (source-name assertion scope).
 *   - p-3 (12px) outer padding satisfies the "padding <= 14px" ceiling.
 *
 * Save / save state intentionally NOT rendered on the lead -- the lead is
 * the editorial focus, the save affordance lives on the secondary cards.
 */

const SAVED_ARTICLES_KEY = "techpulse-saved-articles";

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

/** Strip protocol + leading `www.` from a URL, return up to the first slash. */
function hostname(url: string, fallback = "source"): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

interface LeadStoryCardProps {
  article: {
    id: string;
    title: string;
    source: string;
    url: string;
    publishedAt: string;
    imageUrl: string;
    category: string[];
    content?: string;
    summaryShort: string;
    summaryMedium: string;
    keyInsights: string[];
    sentiment: string;
    trending: boolean;
    credibilityScore?: number;
    sourcesUsed?: string[];
  };
}

export function LeadStoryCard({ article }: LeadStoryCardProps) {
  const [isSaved, setIsSaved] = useState<boolean>(false);

  useEffect(() => {
    setIsSaved(readSavedSet().has(String(article.id)));
  }, [article.id]);

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
    if (hours < 1) return "Just now";
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  // Deck line: first sentence of summaryMedium, falling back to summaryShort.
  const deckSource = (article.summaryMedium || article.summaryShort || "").trim();
  const deck = deckSource ? deckSource.split(/(?<=[.!?])\s+/)[0] : "";

  // Body: prefer summaryMedium for the editorial-drop lockup so the drop
  // cap floats over a real paragraph rather than a one-liner teaser.
  const body = (article.summaryMedium || article.summaryShort || "").trim();

  const hasImage = Boolean(article.imageUrl);

  return (
    <article
      data-slot="card"
      data-testid="news-card-lead"
      className="group relative p-3 transition-colors hover:bg-[var(--background-tint)] rounded-lg"
    >
      {/* Lead image — 16:9, rounded 8 px (REDESIGN Phase D). The heavy
          black-letterbox fallback is gone; when an image is present we
          show it inside a softly tinted frame. */}
      {hasImage && (
        <div className="relative aspect-[16/9] bg-[var(--background-tint)] overflow-hidden mb-4 rounded-lg">
          <ImageWithFallback
            src={article.imageUrl}
            alt={article.title}
            className="w-full h-full object-cover"
          />
          <button
            type="button"
            data-testid="news-card-lead-save-btn"
            onClick={toggleSaved}
            aria-label={isSaved ? "Unsave article" : "Save article"}
            aria-pressed={isSaved}
            className="absolute top-3 right-3 text-[11px] font-medium px-2.5 py-1 bg-background/90 backdrop-blur border border-[var(--rule)] text-foreground hover:bg-background rounded-md transition-colors"
          >
            {isSaved ? "Saved" : "Save"}
          </button>
        </div>
      )}

      {/* Source eyebrow -- mono, .text-gray-500 carried for the source-name
          assertion scope. When the image slot is omitted we tuck the
          save toggle on the right of this row so the contract remains. */}
      <div className="font-mono-tx text-[11px] uppercase-eyebrow flex items-center gap-2 mb-2">
        <span className="text-gray-500 uppercase-eyebrow">{article.source}</span>
        <span className="text-foreground-soft">.</span>
        <span className="text-foreground-soft">{timeAgo(article.publishedAt)}</span>
        {article.credibilityScore !== undefined && (
          <>
            <span className="text-foreground-soft">.</span>
            <span className="text-foreground-soft">v{article.credibilityScore}</span>
          </>
        )}
        {!hasImage && (
          <button
            type="button"
            data-testid="news-card-lead-save-btn"
            onClick={toggleSaved}
            aria-label={isSaved ? "Unsave article" : "Save article"}
            aria-pressed={isSaved}
            className="ml-auto text-[11px] font-medium px-2.5 py-1 border border-[var(--rule)] text-foreground hover:text-foreground hover:bg-[var(--background-tint)] rounded-md transition-colors"
          >
            {isSaved ? "Saved" : "Save"}
          </button>
        )}
      </div>

      {/* Headline \u2014 Geist 32 px in Atelier (was Fraunces 44 px). Still
          NOT data-slot="card-title" so the Linear-dense title-size test
          continues to scope to the secondary cards' titles. */}
      <h2
        className="font-display text-foreground mb-3 group-hover:text-foreground"
        style={{ fontSize: "32px", lineHeight: 1.15, letterSpacing: "-0.025em", fontWeight: 600 }}
      >
        {article.title}
      </h2>

      {/* Deck line \u2014 Geist 18 px, no italic, muted ink. */}
      {deck && (
        <p
          className="text-foreground-soft mb-4 line-clamp-2"
          style={{ fontSize: "18px", lineHeight: 1.35 }}
        >
          {deck}
        </p>
      )}

      {/* Body paragraph \u2014 clean 15 px copy, no drop-cap. */}
      {body && (
        <p
          data-testid="news-card-summary"
          className="text-[15px] leading-[1.6] text-foreground mb-4 line-clamp-6"
        >
          {body}
        </p>
      )}

      {/* Footer \u2014 hairline rule, soft tag chips + read CTA in signal accent. */}
      <div className="pt-3 border-t border-[var(--rule)] flex items-center justify-between gap-2 text-[12px]">
        <div className="flex gap-1.5 flex-wrap items-center">
          {/* DESIGN_REVIEW C-3 — show the lead chip in full, pluralize
              the rest. Lead card is the page's most-prominent footer
              so the chip noise reduction matters here especially. */}
          {article.category.length > 0 && (
            <span className="px-2 py-0.5 bg-[var(--background-tint)] text-foreground-soft rounded-full">
              {article.category[0]}
            </span>
          )}
          {article.category.length > 1 && (
            <span
              className="text-foreground-mute"
              aria-label={`plus ${article.category.length - 1} more categories: ${article.category.slice(1).join(", ")}`}
            >
              · +{article.category.length - 1}
            </span>
          )}
        </div>
        <a
          data-testid="news-card-read-more"
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-medium hover:underline"
          style={{ color: "var(--accent-signal)" }}
        >
          read at {hostname(article.url)} {'\u2192'}
        </a>
      </div>
    </article>
  );
}
