/**
 * UnifiedFeedView — merges Mission Control's dense table and Atelier's
 * card grid into one feed with a single density toggle, per review-07
 * (UX/UI), review-09 (competitive), and review-10 (keep/cut audit): both
 * surfaces rendered the exact same article data as two separately
 * maintained page destinations.
 *
 * `density === 'comfortable'` reuses NewsCard (the Atelier card-grid
 * rendering) inside AtelierShell's centered column. `density ===
 * 'compact'` reuses DenseArticleRow (the Mission Control dense-table
 * rendering) inside MissionShell's list column. Neither rendering path
 * is duplicated here — this component only composes the existing pieces
 * and owns the density switch, loading/empty states, and the optional
 * agent-status rail.
 *
 * The right-rail "agent status" panel (reviewers: worth keeping, not as
 * a permanent fixture) is folded in here as a collapsible element shared
 * across both densities, rather than the Mission-only always-on rail it
 * was before. Its telemetry stays static/idle-by-default — wiring real
 * ingestion events into it is out of scope.
 *
 * Test hooks: data-testid="unified-feed-view", "news-feed-list" (kept
 * from the pre-merge Atelier/Mission markup so existing specs keep
 * scoping to it).
 */
import { ReactNode, useEffect, useMemo, useState } from "react";
import { Loader2, Newspaper } from "lucide-react";
import { toast } from "sonner";
import { NewsCard } from "./NewsCard";
import { AtelierShell } from "./atelier/AtelierShell";
import { MissionShell } from "./mission/MissionShell";
import { DenseArticleRow } from "./mission/DenseArticleRow";
import { AgentTelemetry } from "./mission/AgentTelemetry";
import { readInterestWeights, clearInterestWeights, reorderByInterest } from "../lib/interestWeights";

export type FeedDensity = "comfortable" | "compact";

/**
 * Superset of the article fields NewsCard and DenseArticleRow each read.
 * Both components only touch a subset of this shape, so the same article
 * objects already flowing through App.tsx's `articles`/`filteredArticles`
 * state can be passed straight through without reshaping.
 */
export interface UnifiedFeedArticle {
  id: string;
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  imageUrl?: string;
  category?: string[];
  content?: string;
  summaryShort?: string;
  summaryMedium?: string;
  keyInsights?: string[];
  sentiment?: string;
  trending?: boolean;
  credibilityScore?: number;
  sourcesUsed?: string[];
}

export interface UnifiedFeedViewProps {
  articles: UnifiedFeedArticle[];
  /** 'comfortable' = NewsCard grid, 'compact' = DenseArticleRow table. */
  density: FeedDensity;
  loading?: boolean;
  /** Shown above the list/grid (e.g. "Newsfeed · 47 stories"). */
  heading?: ReactNode;
  /** Overrides the built-in "No articles found" state. */
  emptyState?: ReactNode;
  /** Renders the collapsible agent-status rail. Defaults to true. */
  showAgentStatus?: boolean;
  className?: string;
}

const DefaultEmptyState = (
  <div
    data-testid="news-feed-list"
    className="text-center py-12 border-t border-b border-[var(--rule)] space-y-3"
  >
    <Newspaper className="w-12 h-12 text-foreground mx-auto" />
    <h3 className="font-display text-[22px] font-medium text-foreground">
      No articles found
    </h3>
    <p className="text-[14px] text-foreground-soft">
      Try adjusting your filters or search query
    </p>
  </div>
);

export function UnifiedFeedView({
  articles,
  density,
  loading = false,
  heading,
  emptyState,
  showAgentStatus = true,
  className = "",
}: UnifiedFeedViewProps) {
  const [statusOpen, setStatusOpen] = useState(true);

  const [weights, setWeights] = useState<Record<string, number>>(() => readInterestWeights());
  // Re-read weights only when the feed's *leading* article changes -- a
  // real reload/refresh/filter change -- never on a bare re-render or an
  // infinite-scroll append. `articles` gets a brand-new array reference on
  // most App renders (it's an unmemoized filter in App.tsx) and grows via
  // append during infinite scroll, so keying this off array identity would
  // re-read localStorage -- and pick up any reaction made earlier in the
  // session -- on scroll, silently reshuffling windows already on screen.
  // The leading id is stable across both of those and only moves on a
  // genuine new fetch, so this is a safe proxy for "next feed load".
  const leadingArticleId = articles[0]?.id;
  useEffect(() => {
    setWeights(readInterestWeights());
  }, [leadingArticleId]);
  const orderedArticles = useMemo(() => reorderByInterest(articles, weights), [articles, weights]);
  const isPersonalized = Object.keys(weights).length > 0;

  const handleResetPersonalization = () => {
    clearInterestWeights();
    setWeights({});
    toast.success("Personalization reset — showing latest first");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const personalizationRow = isPersonalized && articles.length > 0 && (
    <div data-testid="personalization-status" className="mb-3 flex items-center justify-between gap-2">
      <span className="font-mono-tx uppercase-eyebrow">
        Personalized for you — based on your reactions
      </span>
      <button
        type="button"
        data-testid="personalization-reset"
        onClick={handleResetPersonalization}
        className="font-mono-tx uppercase-eyebrow underline-offset-4 hover:underline hover:text-foreground transition-colors"
      >
        Reset
      </button>
    </div>
  );

  const body =
    articles.length === 0 ? (
      emptyState ?? DefaultEmptyState
    ) : density === "compact" ? (
      <MissionShell heading={heading} showTelemetry={false}>
        {personalizationRow}
        <div data-testid="news-feed-list" className="flex flex-col">
          {orderedArticles.map((article) => (
            <DenseArticleRow key={article.id} article={article} />
          ))}
        </div>
      </MissionShell>
    ) : (
      <AtelierShell>
        {heading && (
          <div className="mb-4 flex items-center justify-between text-[11px] uppercase tracking-wide text-foreground-mute">
            {heading}
          </div>
        )}
        {personalizationRow}
        <div
          data-testid="news-feed-list"
          className="grid grid-cols-1 lg:grid-cols-3 gap-6"
        >
          {orderedArticles.map((article) => (
            // NewsCard's article prop requires several fields (imageUrl,
            // category, summaryShort, ...) that UnifiedFeedArticle keeps
            // optional so DenseArticleRow's narrower subset also fits.
            // App.tsx's own article state is typed `any[]` for the same
            // reason -- not every ingested article carries every field.
            <NewsCard key={article.id} article={article as any} viewMode="detailed" />
          ))}
        </div>
      </AtelierShell>
    );

  return (
    <div data-testid="unified-feed-view" className={["flex w-full", className].join(" ")}>
      <div className="flex-1 min-w-0">{body}</div>
      {showAgentStatus && articles.length > 0 && (
        <div className="flex shrink-0">
          <button
            type="button"
            data-testid="unified-feed-status-toggle"
            onClick={() => setStatusOpen((v) => !v)}
            aria-expanded={statusOpen}
            aria-controls="unified-feed-agent-status"
            className="self-start px-1.5 py-2 text-[10px] uppercase tracking-wide text-foreground-mute hover:text-foreground border-l border-[var(--rule)] transition-colors"
          >
            {statusOpen ? "›" : "‹"}
          </button>
          {statusOpen && (
            <div id="unified-feed-agent-status">
              <AgentTelemetry />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default UnifiedFeedView;
