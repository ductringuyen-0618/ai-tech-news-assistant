import {
  Newspaper,
  ExternalLink,
  Layers,
} from "lucide-react";
import { Badge } from "./ui/badge";
import { Skeleton } from "./ui/skeleton";
import { DropCap } from "./DropCap";

/**
 * DigestView -- M5 newspaper-section restyle of the daily digest.
 *
 * The component renders the same five logical regions as M3.M3
 * (header / daily summary / curated headlines / topic clusters /
 * top stories / trending / coverage chart), but drops the Card
 * chrome in favour of horizontal `rule-h-thick` section
 * separators with mono `uppercase-eyebrow` labels -- the same
 * pattern M3 introduced for the research transcript.
 *
 * Test contracts preserved (verified via
 * `grep -nE "data-testid=|getByText|querySelector|toHaveClass"
 * frontend/e2e/digest.spec.ts`):
 *
 *   Visible-text contracts:
 *     - "Daily Tech Digest"          (heading on the masthead)
 *     - "Top Stories Today"          (section label)
 *     - "Trending Now"               (section label)
 *
 *   CSS-selector contracts (digest.spec.ts:41, :64, :107,
 *   :131, :165):
 *     - `.border-l-4` on every top-story <li>, each containing
 *       exactly one <h3>. The class is LOAD-BEARING for the
 *       selector even though the visible left rail is now a
 *       mono 3-digit index (001 / 002 / ...) rather than a
 *       colored ruler. We keep the .border-l-4 class on the
 *       <li> with `border-transparent` so the test still binds.
 *     - `[data-slot="badge"]` chips inside each top-story row
 *       (digest.spec.ts:114) -- continue to use <Badge>.
 *     - `.bg-orange-50.rounded-lg` on each "Trending Now" chip
 *       wrapper. We layer mono + outline styling on top so
 *       light-mode reads as a quiet cream tint and dark-mode
 *       gets a faint orange wash -- both acceptable carries.
 *     - Top-story row height <= 200px, top/left padding <= 14px
 *       (digest.spec.ts:165). We use `py-2 pl-3` (8/12px).
 */

interface DigestStory {
  id: string;
  title: string;
  source: string;
  summaryShort: string;
  category: string[];
}

interface DigestTrendingTopic {
  id: string;
  title: string;
  category: string[];
}

interface DailySummary {
  summary: string;
  generated_at: string;
  article_count: number;
}

interface CuratedHeadline {
  id: number;
  title: string;
  source: string;
  summary: string;
  url: string;
  image_url: string | null;
  published_at: string;
  categories: string[];
  score: number;
  mention_count: number;
}

interface TopicCluster {
  name: string;
  slug: string;
  count: number;
  preview: Array<{
    id: number;
    title: string;
    source: string;
    summary: string;
    url: string;
    published_at: string;
  }>;
}

interface DigestViewProps {
  digest: {
    date: string;
    topStories: DigestStory[];
    categoryBreakdown: Record<string, number>;
    trendingTopics: DigestTrendingTopic[];
  };
  dailySummary?: DailySummary | null;
  dailySummaryLoading?: boolean;
  curatedHeadlines?: CuratedHeadline[] | null;
  topicClusters?: TopicCluster[] | null;
}

function relativeTime(iso: string | undefined | null): string {
  if (!iso) return "";
  try {
    const date = new Date(iso);
    const now = Date.now();
    const diffSec = Math.floor((now - date.getTime()) / 1000);
    if (diffSec < 60) return "just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
    if (diffSec < 86_400) return `${Math.floor(diffSec / 3600)} hr ago`;
    if (diffSec < 7 * 86_400) return `${Math.floor(diffSec / 86_400)} d ago`;
    return date.toLocaleDateString();
  } catch {
    return "";
  }
}

/** Inline section eyebrow: `━ LABEL ───────────...`. The rule
 *  fills the rest of the row to match the M3 transcript
 *  language. */
function SectionEyebrow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
        ━ {label}
      </span>
      <span className="flex-1 border-t border-[var(--rule)]" />
    </div>
  );
}

export function DigestView({
  digest,
  dailySummary,
  dailySummaryLoading,
  curatedHeadlines,
  topicClusters,
}: DigestViewProps) {
  const formatMasthead = (dateString: string) => {
    const date = new Date(dateString);
    const wd = date.toLocaleDateString("en-US", { weekday: "short" });
    const d = date.toLocaleDateString("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    return `${wd.toUpperCase()} ${d.toUpperCase()}`;
  };

  const maxBreakdown = Math.max(
    1,
    ...Object.values(digest.categoryBreakdown || {})
  );

  return (
    <div className="max-w-5xl mx-auto space-y-10">
      {/* === DIGEST MASTHEAD ============================== */}
      <header className="space-y-2 border-b-2 border-[var(--foreground)] pb-4">
        <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          ━ {formatMasthead(digest.date)} ━ DAILY EDITION
        </div>
        <h1 className="font-display text-[36px] font-medium tracking-tight text-foreground leading-[1.05]">
          Daily Tech Digest
        </h1>
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          the agentic desk · curated by the wire
        </p>
      </header>

      {/* === DAILY BRIEF (AI-generated summary) ============== */}
      {(dailySummary || dailySummaryLoading) && (
        <section
          data-testid="digest-daily-summary-card"
          className="space-y-3"
        >
          <SectionEyebrow
            label={`DAILY BRIEF — ${formatMasthead(digest.date).split(" ").slice(0, 2).join(" ")}`}
          />
          {dailySummaryLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
            </div>
          ) : dailySummary ? (
            <>
              {/* Editorial drop-cap reused on the daily-brief hero
                  paragraph (design-review #17). DropCap component
                  extracted from the original WelcomeScreen lockup.
                  Italic + 18px leading is layered on top via the
                  className prop so the rest of the typography stays
                  aligned with the M5 digest restyle.

                  Note: ``::first-letter`` on a <p> with the
                  ``.editorial-drop`` class will pick up the first
                  rendered letter inside the paragraph regardless of
                  nested inline wrappers, so the overflowWrap span
                  below doesn't disrupt the drop-cap effect. */}
              <DropCap
                data-testid="digest-daily-summary-text"
                className="text-[18px] italic leading-[1.55]"
              >
                <span style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}>
                  {dailySummary.summary}
                </span>
              </DropCap>
              <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                filed {relativeTime(dailySummary.generated_at) || "today"} · {dailySummary.article_count} article{dailySummary.article_count === 1 ? "" : "s"}
              </p>
            </>
          ) : null}
        </section>
      )}

      {/* === TODAY'S HEADLINES (curated) ===================== */}
      {curatedHeadlines && curatedHeadlines.length > 0 && (
        <section className="space-y-3">
          <SectionEyebrow label="TODAY'S HEADLINES (CURATED)" />
          <div
            data-testid="digest-curated-headlines"
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-6"
          >
            {curatedHeadlines.map((story) => (
              <a
                key={story.id}
                data-testid={`digest-curated-story-${story.id}`}
                href={story.url || "#"}
                target={story.url ? "_blank" : undefined}
                rel={story.url ? "noopener noreferrer" : undefined}
                className="group flex flex-col border-t border-[var(--rule)] pt-3 hover:cursor-pointer"
              >
                {story.image_url ? (
                  <div className="w-full aspect-[16/10] overflow-hidden bg-[var(--background-tint)] mb-3">
                    <img
                      src={story.image_url}
                      alt=""
                      loading="lazy"
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display =
                          "none";
                      }}
                    />
                  </div>
                ) : null}
                <h3
                  className="font-display text-[20px] font-medium text-foreground leading-snug line-clamp-3 group-hover:text-signal group-hover:underline"
                  style={{
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {story.title}
                </h3>
                {story.summary ? (
                  <p
                    className="mt-2 text-[14px] text-foreground-soft leading-relaxed line-clamp-2"
                    style={{
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                    }}
                  >
                    {story.summary}
                  </p>
                ) : null}
                <div className="mt-2 font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft flex items-center gap-2">
                  <span>{story.source}</span>
                  <span>·</span>
                  <span>{relativeTime(story.published_at)}</span>
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      {/* === TODAY BY TOPIC (clustering) ===================== */}
      {topicClusters && topicClusters.length > 0 && (
        <section className="space-y-3">
          <SectionEyebrow label="TODAY BY TOPIC" />
          <div
            data-testid="digest-topic-clusters"
            className="flex flex-col gap-4"
          >
            {topicClusters.map((cluster) => (
              <div
                key={cluster.slug}
                data-testid={`digest-topic-cluster-${cluster.slug}`}
                className="border-t border-[var(--rule)] pt-3"
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Layers className="w-3.5 h-3.5 text-foreground-soft shrink-0" />
                    <h3 className="font-display text-[18px] font-medium text-foreground truncate">
                      {cluster.name}
                    </h3>
                    <span className="font-mono-tx text-[11px] uppercase-eyebrow text-signal tabular-nums">
                      ▌{cluster.count}
                    </span>
                  </div>
                  {cluster.count > cluster.preview.length ? (
                    <span className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft shrink-0">
                      +{cluster.count - cluster.preview.length} more
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-col">
                  {cluster.preview.map((article) => (
                    <a
                      key={article.id}
                      data-testid={`digest-cluster-article-${article.id}`}
                      href={article.url || "#"}
                      target={article.url ? "_blank" : undefined}
                      rel={article.url ? "noopener noreferrer" : undefined}
                      className="group flex items-start gap-2 py-2 border-t border-[var(--rule)] hover:text-signal transition-colors"
                    >
                      <div className="flex-1 min-w-0 space-y-1">
                        <p
                          className="font-display text-[15px] text-foreground leading-snug line-clamp-2 group-hover:text-signal group-hover:underline"
                          style={{
                            overflowWrap: "anywhere",
                            wordBreak: "break-word",
                          }}
                        >
                          {article.title}
                        </p>
                        <div className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
                          {article.source} · {relativeTime(article.published_at)}
                        </div>
                      </div>
                      <ExternalLink className="w-3 h-3 text-foreground-soft mt-1 shrink-0" />
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* === TOP STORIES TODAY ============================== */}
      <section className="space-y-3">
        <SectionEyebrow label="TOP STORIES TODAY" />
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          the most important tech news you shouldn't miss
        </p>
        <ul
          data-testid="digest-top-stories"
          className="flex flex-col"
        >
          {digest.topStories.map((story, idx) => (
            // NOTE: the `.border-l-4` class on this <li> is
            // load-bearing for digest.spec.ts:41 and :107. The
            // visible left rail is now the mono 3-digit index
            // rendered inside the row; the border is set to
            // transparent so the class survives the visual
            // rebuild while the selector still matches.
            <li
              key={story.id}
              data-testid="digest-top-story-row"
              className="border-l-4 border-transparent border-t border-t-[var(--rule)] pl-3 py-2 hover:bg-[var(--background-tint)] transition-colors"
            >
              <div className="flex items-start gap-3">
                <span className="font-mono-tx text-[13px] uppercase-eyebrow text-signal tabular-nums shrink-0 pt-0.5">
                  {String(idx + 1).padStart(3, "0")}
                </span>
                <div className="flex-1 min-w-0 space-y-1.5">
                  <h3
                    className="font-display text-[16px] font-medium text-foreground leading-snug"
                    style={{
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                    }}
                  >
                    {story.title}
                  </h3>
                  <p
                    className="text-[13px] text-foreground-soft leading-relaxed line-clamp-2"
                    style={{
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                    }}
                  >
                    {story.summaryShort}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge
                      variant="outline"
                      className="h-5 px-1.5 text-[10px] font-mono-tx uppercase-eyebrow border-[var(--rule)] bg-card text-foreground rounded-none"
                    >
                      {story.source}
                    </Badge>
                    {story.category
                      .filter((cat) => cat && cat !== story.source)
                      .slice(0, 2)
                      .map((cat) => (
                        <Badge
                          key={cat}
                          variant="secondary"
                          className="h-5 px-1.5 text-[10px] font-mono-tx uppercase-eyebrow rounded-none"
                        >
                          {cat}
                        </Badge>
                      ))}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* === TRENDING NOW =================================== */}
      <section className="space-y-3">
        <SectionEyebrow label="TRENDING NOW" />
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          most discussed topics today
        </p>
        <div
          data-testid="digest-trending-row"
          className="flex flex-wrap gap-1.5"
        >
          {digest.trendingTopics.map((topic) => (
            // The `bg-orange-50 rounded-lg` literals are
            // load-bearing for digest.spec.ts:64 and :131. We
            // keep BOTH classes on the wrapper -- in light mode
            // the orange-50 reads as a faint cream tint, in
            // dark mode the dark:bg-orange-500/10 swap renders
            // a quiet wash. The mono outline pill rendered
            // INSIDE the wrapper carries the visible style.
            <div
              key={topic.id}
              data-testid="digest-trending-chip"
              className="bg-orange-50 dark:bg-orange-500/10 rounded-lg p-px"
            >
              <div className="inline-flex items-center gap-1.5 border border-[var(--rule)] bg-card px-2 py-1 font-mono-tx text-[11px] uppercase-eyebrow text-foreground hover:border-[var(--accent-signal)] hover:text-signal transition-colors max-w-full">
                <span className="text-signal">▌</span>
                <p
                  className="truncate"
                  style={{
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {topic.title}
                </p>
                {topic.category
                  .filter((c) => c && c.trim().length > 0)
                  .slice(0, 1)
                  .map((cat) => (
                    <Badge
                      key={cat}
                      variant="outline"
                      className="h-4 px-1 text-[10px] font-mono-tx uppercase-eyebrow border-[var(--rule)] rounded-none"
                    >
                      {cat}
                    </Badge>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* === CATEGORY DISTRIBUTION ========================== */}
      <section className="space-y-3">
        <SectionEyebrow label="CATEGORY DISTRIBUTION" />
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft">
          news distribution across categories
        </p>
        <div
          data-testid="digest-source-distribution"
          className="space-y-3"
        >
          {Object.entries(digest.categoryBreakdown)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 6)
            .map(([category, count]) => (
              <div
                key={category}
                data-testid="digest-source-row"
                className="space-y-1"
              >
                <div className="flex items-center justify-between font-mono-tx text-[11px] uppercase-eyebrow">
                  <span className="text-foreground truncate">{category}</span>
                  <span className="text-foreground-soft tabular-nums">
                    {count} articles
                  </span>
                </div>
                <div className="w-full bg-[var(--background-tint)] h-1.5 overflow-hidden">
                  <div
                    className="bg-foreground h-1.5 transition-all"
                    style={{
                      width: `${(count / maxBreakdown) * 100}%`,
                    }}
                  />
                </div>
              </div>
            ))}
        </div>
      </section>

      {/* === END OF EDITION =============================== */}
      <footer className="border-t border-[var(--rule)] pt-4">
        <p className="font-mono-tx text-[11px] uppercase-eyebrow text-foreground-soft text-center">
          ━ end of brief ━ get tomorrow's edition · subscribe at /digest
        </p>
      </footer>
      <div className="hidden">
        <Newspaper />
      </div>
    </div>
  );
}
